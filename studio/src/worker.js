// Naad Katha Studio: API + static app on one Cloudflare Worker.
//
// People sign in through Cloudflare Access (Google). The Worker checks the
// Access token, then looks the email up in the `members` table: only invited
// people get in, and their role decides what they can do.
// The sync job (run by the Claude project) talks to /api/sync/* with a
// bearer token instead.

const ROLES = ['viewer', 'editor', 'manager', 'owner'];
const rank = (r) => ROLES.indexOf(r);
const can = {
  approve: (r) => rank(r) >= rank('manager'),
  note: (r) => rank(r) >= rank('editor'),
  members: (r) => r === 'owner',
};

const now = () => new Date().toISOString();
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
const err = (status, message) => json({ error: message }, status);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith('/api/sync/')) return await syncApi(request, env, url);
      if (url.pathname.startsWith('/api/')) return await userApi(request, env, url);
      return env.ASSETS.fetch(request);
    } catch (e) {
      if (e instanceof HttpError) return err(e.status, e.message);
      console.error(e);
      return err(500, 'Something went wrong');
    }
  },
};

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// ---------------------------------------------------------------- auth

let jwksCache = { at: 0, keys: null };

async function accessEmail(request, env) {
  if (env.ENVIRONMENT === 'dev') {
    return (request.headers.get('x-dev-user') || env.DEV_USER_EMAIL || '').toLowerCase() || null;
  }
  const token =
    request.headers.get('cf-access-jwt-assertion') || cookie(request, 'CF_Authorization');
  if (!token) return null;
  const payload = await verifyAccessJwt(token, env);
  return payload && payload.email ? String(payload.email).toLowerCase() : null;
}

function cookie(request, name) {
  const c = request.headers.get('cookie') || '';
  const m = c.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? m[1] : null;
}

const b64urlBytes = (s) =>
  Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), (c) =>
    c.charCodeAt(0),
  );

async function verifyAccessJwt(token, env) {
  const [h, p, s] = token.split('.');
  if (!h || !p || !s) return null;
  const header = JSON.parse(new TextDecoder().decode(b64urlBytes(h)));
  const payload = JSON.parse(new TextDecoder().decode(b64urlBytes(p)));
  if (Date.now() - jwksCache.at > 3600_000 || !jwksCache.keys) {
    const r = await fetch(`https://${env.ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`);
    jwksCache = { at: Date.now(), keys: (await r.json()).keys };
  }
  const jwk = jwksCache.keys.find((k) => k.kid === header.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const ok = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    key,
    b64urlBytes(s),
    new TextEncoder().encode(`${h}.${p}`),
  );
  if (!ok) return null;
  const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!aud.includes(env.ACCESS_AUD)) return null;
  if (payload.exp && payload.exp * 1000 < Date.now()) return null;
  return payload;
}

// The owner named in OWNER_EMAIL is always the owner of the default channel.
async function ensureBootstrap(env) {
  const id = env.DEFAULT_CHANNEL_ID || 'naad-katha';
  await env.DB.prepare('INSERT OR IGNORE INTO channels (id, name) VALUES (?, ?)')
    .bind(id, env.DEFAULT_CHANNEL_NAME || 'Naad Katha')
    .run();
  if (env.OWNER_EMAIL) {
    await env.DB.prepare(
      `INSERT INTO members (channel_id, email, name, role, added_by, added_at)
       VALUES (?, ?, ?, 'owner', 'setup', ?)
       ON CONFLICT(channel_id, email) DO UPDATE SET role = 'owner'`,
    )
      .bind(id, env.OWNER_EMAIL.toLowerCase(), env.OWNER_NAME || 'Owner', now())
      .run();
  }
}

async function membership(env, email, channelId) {
  return env.DB.prepare('SELECT * FROM members WHERE channel_id = ? AND email = ?')
    .bind(channelId, email)
    .first();
}

// ---------------------------------------------------------------- user API

async function userApi(request, env, url) {
  await ensureBootstrap(env);
  const email = await accessEmail(request, env);
  if (!email) return err(401, 'Please sign in');

  const parts = url.pathname.split('/').filter(Boolean); // ['api', ...]
  const method = request.method;

  if (parts[1] === 'me' && method === 'GET') {
    const { results } = await env.DB.prepare(
      `SELECT c.id, c.name, c.timezone, c.post_time, c.last_sync_at, m.role, m.name AS member_name
       FROM members m JOIN channels c ON c.id = m.channel_id WHERE m.email = ? ORDER BY c.name`,
    )
      .bind(email)
      .all();
    return json({ email, name: results[0]?.member_name || null, channels: results });
  }

  if (parts[1] !== 'channels' || !parts[2]) return err(404, 'Not found');
  const channelId = parts[2];
  const me = await membership(env, email, channelId);
  if (!me) return err(403, 'You have not been added to this channel yet. Ask the owner to invite you.');
  const channel = await env.DB.prepare('SELECT * FROM channels WHERE id = ?').bind(channelId).first();
  const actor = { email, name: me.name || email, role: me.role };

  // /api/channels/:cid/posts
  if (parts[3] === 'posts' && !parts[4] && method === 'GET') {
    const { results } = await env.DB.prepare(
      `SELECT p.id, p.folder, p.slug, p.post_date, p.title, p.hook, p.first_line, p.video_key, p.cover_key,
              p.video_sha, a.state AS a_state, a.write_state AS a_write, a.by_name AS a_by, a.at AS a_at,
              (SELECT COUNT(*) FROM notes n WHERE n.post_id = p.id) AS note_count
       FROM posts p LEFT JOIN approvals a ON a.post_id = p.id
       WHERE p.channel_id = ? ORDER BY p.post_date IS NULL, p.post_date`,
    )
      .bind(channelId)
      .all();
    const today = localDate(channel.timezone);
    return json({
      channel,
      me: actor,
      today,
      posts: results.map((p) => ({ ...p, status: statusOf(p, today) })),
    });
  }

  // /api/channels/:cid/posts/:pid[/action]
  if (parts[3] === 'posts' && parts[4]) {
    const postId = `${channelId}:${decodeURIComponent(parts[4])}`;
    const post = await env.DB.prepare(
      `SELECT p.*, a.state AS a_state, a.write_state AS a_write, a.by_name AS a_by, a.at AS a_at,
              a.write_msg AS a_msg, a.video_sha AS a_sha
       FROM posts p LEFT JOIN approvals a ON a.post_id = p.id WHERE p.id = ?`,
    )
      .bind(postId)
      .first();
    if (!post) return err(404, 'Post not found');
    const today = localDate(channel.timezone);
    const action = parts[5];

    if (!action && method === 'GET') {
      const notes = await env.DB.prepare('SELECT * FROM notes WHERE post_id = ? ORDER BY at').bind(postId).all();
      const events = await env.DB.prepare(
        'SELECT * FROM events WHERE post_id = ? ORDER BY at DESC LIMIT 30',
      )
        .bind(postId)
        .all();
      return json({
        channel,
        me: actor,
        post: { ...post, status: statusOf(post, today), checks: checksFor(post) },
        notes: notes.results,
        events: events.results,
      });
    }

    if (action === 'approve' && method === 'POST') {
      if (!can.approve(actor.role)) return err(403, 'Only the owner or a manager can approve');
      if (!post.video_key) return err(400, 'There is no video for this post yet');
      if (post.post_date && post.post_date < today) return err(400, 'This post date has passed');
      const body = await request.json().catch(() => ({}));
      if (body.video_sha && body.video_sha !== post.video_sha)
        return err(409, 'The video changed while you were watching. Reload and check the new one.');
      await env.DB.prepare(
        `INSERT INTO approvals (post_id, state, by_email, by_name, role, at, video_sha, write_state)
         VALUES (?, 'approved', ?, ?, ?, ?, ?, 'pending')
         ON CONFLICT(post_id) DO UPDATE SET state='approved', by_email=excluded.by_email, by_name=excluded.by_name,
           role=excluded.role, at=excluded.at, video_sha=excluded.video_sha, write_state='pending', write_msg=NULL, written_at=NULL`,
      )
        .bind(postId, actor.email, actor.name, actor.role, now(), post.video_sha)
        .run();
      await logEvent(env, channelId, postId, actor.email, 'approved', `video ${String(post.video_sha).slice(0, 8)}`);
      return json({ ok: true });
    }

    if (action === 'unapprove' && method === 'POST') {
      if (!can.approve(actor.role)) return err(403, 'Only the owner or a manager can do this');
      if (post.post_date && post.post_date < today) return err(400, 'This post date has passed');
      await env.DB.prepare(
        `INSERT INTO approvals (post_id, state, by_email, by_name, role, at, video_sha, write_state)
         VALUES (?, 'unapproved', ?, ?, ?, ?, ?, 'pending')
         ON CONFLICT(post_id) DO UPDATE SET state='unapproved', by_email=excluded.by_email, by_name=excluded.by_name,
           role=excluded.role, at=excluded.at, write_state='pending', write_msg=NULL, written_at=NULL`,
      )
        .bind(postId, actor.email, actor.name, actor.role, now(), post.video_sha)
        .run();
      await logEvent(env, channelId, postId, actor.email, 'unapproved', null);
      return json({ ok: true });
    }

    if (action === 'notes' && method === 'POST') {
      if (!can.note(actor.role)) return err(403, 'Viewers cannot leave notes');
      const body = await request.json().catch(() => ({}));
      const text = String(body.text || '').trim().slice(0, 2000);
      if (!text) return err(400, 'Write something first');
      await env.DB.prepare('INSERT INTO notes (post_id, email, name, text, at) VALUES (?, ?, ?, ?, ?)')
        .bind(postId, actor.email, actor.name, text, now())
        .run();
      await logEvent(env, channelId, postId, actor.email, 'note', text.slice(0, 120));
      return json({ ok: true });
    }
    return err(404, 'Not found');
  }

  // /api/channels/:cid/media/<key>
  if (parts[3] === 'media' && method === 'GET') {
    const key = `${channelId}/${parts.slice(4).map(decodeURIComponent).join('/')}`;
    return serveMedia(request, env, key);
  }

  // /api/channels/:cid/members
  if (parts[3] === 'members') {
    if (method === 'GET') {
      const { results } = await env.DB.prepare(
        "SELECT email, name, role, added_at FROM members WHERE channel_id = ? ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 WHEN 'editor' THEN 2 ELSE 3 END, name",
      )
        .bind(channelId)
        .all();
      return json({ me: actor, members: results });
    }
    if (!can.members(actor.role)) return err(403, 'Only the owner can change the team');
    if (method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const mEmail = String(body.email || '').trim().toLowerCase();
      const role = String(body.role || 'viewer');
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mEmail)) return err(400, 'That email does not look right');
      if (!['manager', 'editor', 'viewer'].includes(role)) return err(400, 'Pick manager, editor or viewer');
      if (env.OWNER_EMAIL && mEmail === env.OWNER_EMAIL.toLowerCase()) return err(400, 'That is the owner');
      await env.DB.prepare(
        `INSERT INTO members (channel_id, email, name, role, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(channel_id, email) DO UPDATE SET role = excluded.role, name = COALESCE(excluded.name, members.name)`,
      )
        .bind(channelId, mEmail, String(body.name || '').trim() || null, role, actor.email, now())
        .run();
      await logEvent(env, channelId, null, actor.email, 'member_set', `${mEmail} as ${role}`);
      return json({ ok: true });
    }
    if (method === 'DELETE' && parts[4]) {
      const mEmail = decodeURIComponent(parts[4]).toLowerCase();
      if (mEmail === actor.email) return err(400, 'You cannot remove yourself');
      await env.DB.prepare("DELETE FROM members WHERE channel_id = ? AND email = ? AND role != 'owner'")
        .bind(channelId, mEmail)
        .run();
      await logEvent(env, channelId, null, actor.email, 'member_removed', mEmail);
      return json({ ok: true });
    }
  }
  return err(404, 'Not found');
}

async function serveMedia(request, env, key) {
  const range = request.headers.get('range');
  let opts = {};
  if (range) {
    const m = range.match(/bytes=(\d*)-(\d*)/);
    if (m) {
      const start = m[1] ? Number(m[1]) : undefined;
      const end = m[2] ? Number(m[2]) : undefined;
      if (start !== undefined) opts.range = end !== undefined ? { offset: start, length: end - start + 1 } : { offset: start };
      else if (end !== undefined) opts.range = { suffix: end };
    }
  }
  const obj = await env.MEDIA.get(key, opts);
  if (!obj) return err(404, 'File not found');
  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set('accept-ranges', 'bytes');
  headers.set('cache-control', 'private, max-age=3600');
  if (opts.range && obj.range) {
    const offset = obj.range.offset ?? obj.size - obj.range.length;
    const length = obj.range.length ?? obj.size - offset;
    headers.set('content-range', `bytes ${offset}-${offset + length - 1}/${obj.size}`);
    headers.set('content-length', String(length));
    return new Response(obj.body, { status: 206, headers });
  }
  headers.set('content-length', String(obj.size));
  return new Response(obj.body, { headers });
}

// ---------------------------------------------------------------- status + checks

function localDate(tz) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: tz || 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

function statusOf(p, today) {
  const fileApproved = /^FINAL CUT\./i.test(p.first_line || '');
  if (!p.post_date) return 'parked';
  if (p.a_state && p.a_write === 'pending') return p.a_state === 'approved' ? 'approving' : 'unapproving';
  if (p.a_state && p.a_write === 'failed') return 'approval_failed';
  if (p.post_date < today) return fileApproved ? 'posted' : 'missed';
  if (fileApproved) return 'approved';
  if (p.video_key) return 'review';
  return 'in_progress';
}

// Light, automatic pre-approval checks taken from the channel's standing rules.
function checksFor(p) {
  const out = [];
  const d = p.description || '';
  const tagsAtEnd = /#\w+/.test(d);
  out.push({ ok: tagsAtEnd, label: 'Hashtags inside the caption' });
  out.push({ ok: /srot|source|स्रोत|Bhagavad Gita|Purana|Ramayan|Mahabharat/i.test(d), label: 'Source line in the caption' });
  const asks = (d.match(/comment kar|comment mein|like kar|subscribe|follow kar|bhejiye|share kar/gi) || []).length;
  out.push({ ok: asks <= 1, label: asks <= 1 ? 'One viewer ask only' : `${asks} viewer asks found, rule is one` });
  out.push({ ok: !!p.title, label: 'Title written' });
  out.push({ ok: !!p.video_key, label: 'Video uploaded' });
  out.push({ ok: !!p.cover_key, label: 'Cover image present' });
  return out;
}

async function logEvent(env, channelId, postId, email, kind, detail) {
  await env.DB.prepare('INSERT INTO events (channel_id, post_id, email, kind, detail, at) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(channelId, postId, email, kind, detail, now())
    .run();
}

// ---------------------------------------------------------------- sync API

async function syncApi(request, env, url) {
  const auth = request.headers.get('authorization') || '';
  if (!env.SYNC_TOKEN || auth !== `Bearer ${env.SYNC_TOKEN}`) return err(401, 'Bad sync token');
  await ensureBootstrap(env);
  const parts = url.pathname.split('/').filter(Boolean); // api sync :cid ...
  const channelId = parts[2];
  const channel = await env.DB.prepare('SELECT * FROM channels WHERE id = ?').bind(channelId).first();
  if (!channel) return err(404, 'Unknown channel');
  const method = request.method;

  // Upsert post metadata from the post folders.
  if (parts[3] === 'posts' && method === 'POST') {
    const body = await request.json();
    const stmts = [];
    const seen = [];
    for (const p of body.posts || []) {
      const id = `${channelId}:${p.folder}`;
      seen.push(id);
      stmts.push(
        env.DB.prepare(
          `INSERT INTO posts (id, channel_id, folder, slug, post_date, title, hook, description, settings, structure,
             beats_json, first_line, video_key, video_sha, video_bytes, cover_key, folder_mtime, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, post_date=excluded.post_date, title=excluded.title,
             hook=excluded.hook, description=excluded.description, settings=excluded.settings, structure=excluded.structure,
             beats_json=excluded.beats_json, first_line=excluded.first_line, video_key=excluded.video_key,
             video_sha=excluded.video_sha, video_bytes=excluded.video_bytes, cover_key=excluded.cover_key,
             folder_mtime=excluded.folder_mtime, updated_at=excluded.updated_at`,
        ).bind(
          id, channelId, p.folder, p.slug, p.post_date || null, p.title || null, p.hook || null,
          p.description || null, p.settings || null, p.structure || null,
          p.beats ? JSON.stringify(p.beats) : null, p.first_line || null, p.video_key || null,
          p.video_sha || null, p.video_bytes || null, p.cover_key || null, p.folder_mtime || null, now(),
        ),
      );
    }
    if (body.full && seen.length) {
      // Folders that disappeared are removed from the plan.
      const placeholders = seen.map(() => '?').join(',');
      stmts.push(
        env.DB.prepare(`DELETE FROM posts WHERE channel_id = ? AND id NOT IN (${placeholders})`).bind(channelId, ...seen),
      );
    }
    stmts.push(env.DB.prepare('UPDATE channels SET last_sync_at = ? WHERE id = ?').bind(now(), channelId));
    await env.DB.batch(stmts);
    return json({ ok: true, count: seen.length });
  }

  // Which media keys already exist (so the sync only uploads changes).
  if (parts[3] === 'media-index' && method === 'GET') {
    const out = {};
    let cursor;
    do {
      const list = await env.MEDIA.list({ prefix: `${channelId}/`, cursor, include: ['customMetadata'] });
      for (const o of list.objects) out[o.key.slice(channelId.length + 1)] = o.customMetadata?.sha || null;
      cursor = list.truncated ? list.cursor : undefined;
    } while (cursor);
    return json({ keys: out });
  }

  // Upload one media file: PUT /api/sync/:cid/media/<key>?sha=...
  if (parts[3] === 'media' && (method === 'PUT' || method === 'DELETE')) {
    const key = `${channelId}/${parts.slice(4).map(decodeURIComponent).join('/')}`;
    if (method === 'DELETE') {
      await env.MEDIA.delete(key);
      return json({ ok: true });
    }
    const type = request.headers.get('content-type') || 'application/octet-stream';
    await env.MEDIA.put(key, request.body, {
      httpMetadata: { contentType: type },
      customMetadata: { sha: url.searchParams.get('sha') || '' },
    });
    return json({ ok: true, key });
  }

  // Approvals waiting to be written into upload-text.md.
  if (parts[3] === 'approvals' && !parts[4] && method === 'GET') {
    const { results } = await env.DB.prepare(
      `SELECT a.*, p.folder, p.video_sha AS current_sha FROM approvals a JOIN posts p ON p.id = a.post_id
       WHERE p.channel_id = ? AND a.write_state = 'pending'`,
    )
      .bind(channelId)
      .all();
    return json({ approvals: results });
  }

  // POST /api/sync/:cid/approvals/<folder>/ack {ok, msg, first_line}
  if (parts[3] === 'approvals' && parts[4] && method === 'POST') {
    const postId = `${channelId}:${decodeURIComponent(parts[4])}`;
    const body = await request.json();
    await env.DB.prepare('UPDATE approvals SET write_state = ?, write_msg = ?, written_at = ? WHERE post_id = ?')
      .bind(body.ok ? 'written' : 'failed', body.msg || null, now(), postId)
      .run();
    if (body.first_line)
      await env.DB.prepare('UPDATE posts SET first_line = ? WHERE id = ?').bind(body.first_line, postId).run();
    await logEvent(env, channelId, postId, 'sync', body.ok ? 'approval_written' : 'approval_failed', body.msg || null);
    return json({ ok: true });
  }

  return err(404, 'Not found');
}
