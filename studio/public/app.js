// Naad Katha Studio front end. Plain JS, no build step.

const $app = document.getElementById('app');
const $channel = document.getElementById('channel');
const state = { me: null, channelId: null };

const STATUS = {
  review: 'Ready for review',
  approved: 'Approved',
  approving: 'Approval being saved',
  unapproving: 'Unapproval being saved',
  approval_failed: 'Approval not saved',
  posted: 'Posted',
  missed: 'Date passed',
  in_progress: 'In progress',
  parked: 'Parked',
};
const ROLE_HELP = {
  owner: 'Everything, including the team',
  manager: 'Review, notes and approve',
  editor: 'Review and leave notes',
  viewer: 'Look only',
};

// ------------------------------------------------------------ helpers
const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function md(text) {
  // Tiny, safe markdown: headings, bullets, bold, line breaks.
  const lines = esc(text || '').split('\n');
  let html = '', inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${bullet[1]}</li>`;
      continue;
    }
    if (inList) { html += '</ul>'; inList = false; }
    const h = line.match(/^#{1,4}\s+(.*)$/);
    if (h) html += `<h3>${h[1]}</h3>`;
    else if (line.trim()) html += `<p>${line}</p>`;
  }
  if (inList) html += '</ul>';
  return html;
}

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const parseDay = (iso) => new Date(`${iso}T12:00:00Z`);
const dayLabel = (iso) => {
  const d = parseDay(iso);
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
};
const addDays = (iso, n) => {
  const d = parseDay(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const fmtTime = (hhmm) => {
  const [h, m] = String(hhmm || '18:00').split(':').map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
};
const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
};
const chip = (s) => `<span class="chip s-${esc(s)}">${esc(STATUS[s] || s)}</span>`;
const mediaUrl = (key) => `/api/channels/${encodeURIComponent(state.channelId)}/media/${key.split('/').map(encodeURIComponent).join('/')}`;

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.hidden = true), 3500);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'content-type': 'application/json', ...(opts.headers || {}) },
    credentials: 'same-origin',
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || `Error ${r.status}`), { status: r.status });
  return data;
}

function setTab(name) {
  document.querySelectorAll('#tabs a').forEach((a) => a.classList.toggle('on', a.dataset.tab === name));
}

// ------------------------------------------------------------ boot
async function boot() {
  try {
    state.me = await api('/api/me');
  } catch (e) {
    $app.innerHTML = `<div class="empty"><p>${esc(e.message)}</p></div>`;
    return;
  }
  const chans = state.me.channels;
  if (!chans.length) {
    $app.innerHTML = `<div class="empty"><h1>Namaste</h1><p>You are signed in as ${esc(state.me.email)}, but nobody has added you to a channel yet.</p><p>Ask the channel owner to invite this email.</p></div>`;
    document.getElementById('tabs').hidden = true;
    return;
  }
  let saved = null;
  try { saved = localStorage.getItem('nk.channel'); } catch {}
  state.channelId = chans.some((c) => c.id === saved) ? saved : chans[0].id;
  if (chans.length > 1) {
    $channel.hidden = false;
    $channel.innerHTML = chans.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');
    $channel.value = state.channelId;
    $channel.onchange = () => {
      state.channelId = $channel.value;
      try { localStorage.setItem('nk.channel', state.channelId); } catch {}
      route();
    };
  }
  window.addEventListener('hashchange', route);
  route();
}

function route() {
  const h = location.hash.replace(/^#\/?/, '');
  const [page, arg] = h.split('/');
  window.scrollTo(0, 0);
  if (page === 'post' && arg) return showPost(decodeURIComponent(arg));
  if (page === 'review') return showReview();
  if (page === 'team') return showTeam();
  return showPlan();
}

async function loadPosts() {
  const data = await api(`/api/channels/${encodeURIComponent(state.channelId)}/posts`);
  const waiting = data.posts.filter((p) => ['review', 'approval_failed'].includes(p.status) && p.post_date >= data.today).length;
  const c = document.getElementById('review-count');
  c.hidden = !waiting;
  c.textContent = waiting;
  return data;
}

// ------------------------------------------------------------ plan
async function showPlan() {
  setTab('plan');
  const data = await loadPosts().catch(fail);
  if (!data) return;
  const { channel, posts, today } = data;
  const byDate = new Map();
  for (const p of posts) if (p.post_date) (byDate.get(p.post_date) || byDate.set(p.post_date, []).get(p.post_date)).push(p);
  const lastDated = posts.filter((p) => p.post_date).map((p) => p.post_date).sort().at(-1) || today;
  const horizon = [addDays(today, 13), lastDated].sort().at(-1);

  let upcoming = '';
  for (let d = today; d <= horizon; d = addDays(d, 1)) {
    const list = byDate.get(d) || [];
    const dd = parseDay(d);
    const dateCol = `<div class="date ${d === today ? 'today' : ''}"><div class="dow">${d === today ? 'Today' : DOW[dd.getUTCDay()]}</div><div class="dnum">${dd.getUTCDate()}</div><div class="mon">${MON[dd.getUTCMonth()]}</div></div>`;
    if (!list.length) {
      upcoming += `<div class="day">${dateCol}<div class="card open">Open slot, nothing planned yet</div></div>`;
      continue;
    }
    upcoming += `<div class="day">${dateCol}<div>${list.map(postCard).join('<div style="height:8px"></div>')}</div></div>`;
  }
  const past = posts.filter((p) => p.post_date && p.post_date < today).reverse();
  const parked = posts.filter((p) => !p.post_date);

  $app.innerHTML = `
    <h1>${esc(channel.name)} plan</h1>
    <p class="sync">Posts daily at ${fmtTime(channel.post_time)}. Last updated from the post folders ${esc(ago(channel.last_sync_at))}.</p>
    <h2>Next two weeks</h2>
    ${upcoming}
    ${parked.length ? `<h2>Parked</h2>${parked.map((p) => `<div style="margin-bottom:8px">${postCard(p)}</div>`).join('')}` : ''}
    ${past.length ? `<details class="earlier"><summary>Earlier posts (${past.length})</summary>${past
      .map((p) => `<div class="day"><div class="date"><div class="dow">${DOW[parseDay(p.post_date).getUTCDay()]}</div><div class="dnum">${parseDay(p.post_date).getUTCDate()}</div><div class="mon">${MON[parseDay(p.post_date).getUTCMonth()]}</div></div>${postCard(p)}</div>`)
      .join('')}</details>` : ''}`;
}

function postCard(p) {
  return `<a class="card" href="#/post/${encodeURIComponent(p.folder)}">
    <div class="row">${chip(p.status)}${p.note_count ? `<span class="muted" style="font-size:12px">${p.note_count} note${p.note_count > 1 ? 's' : ''}</span>` : ''}</div>
    <div class="title">${esc(p.title || p.slug)}</div>
    ${p.hook ? `<div class="hook">${esc(p.hook)}</div>` : ''}
  </a>`;
}

// ------------------------------------------------------------ review queue
async function showReview() {
  setTab('review');
  const data = await loadPosts().catch(fail);
  if (!data) return;
  const list = data.posts
    .filter((p) => p.post_date && p.post_date >= data.today && ['review', 'approval_failed', 'approving'].includes(p.status))
    .sort((a, b) => a.post_date.localeCompare(b.post_date));
  $app.innerHTML = `
    <h1>Waiting for a decision</h1>
    <p class="sync">Approve by 4:00 pm on the post day so the ${fmtTime(data.channel.post_time)} post goes out.</p>
    ${list.length ? list.map((p) => `<div style="margin-top:12px"><div class="label">Approve by 4:00 pm, ${esc(dayLabel(p.post_date))}</div>${postCard(p)}</div>`).join('') : '<div class="empty">Nothing is waiting. 🙏</div>'}`;
}

// ------------------------------------------------------------ post
async function showPost(folder) {
  setTab('plan');
  let data;
  try {
    data = await api(`/api/channels/${encodeURIComponent(state.channelId)}/posts/${encodeURIComponent(folder)}`);
  } catch (e) { return fail(e); }
  const { post, me, notes, events, channel } = data;
  const canApprove = me.role === 'owner' || me.role === 'manager';
  const canNote = me.role !== 'viewer';
  const beats = post.beats_json ? JSON.parse(post.beats_json) : [];
  const approvedInFile = /^FINAL CUT\./i.test(post.first_line || '');
  const future = post.post_date && post.status !== 'posted' && post.status !== 'missed';
  const failing = post.checks.filter((c) => !c.ok);

  let approveHtml = '';
  if (post.status === 'approving') approveHtml = `<p>Approved by ${esc(post.a_by)}. Saving it to the post folder now, this takes up to 15 minutes.</p>`;
  else if (post.status === 'unapproving') approveHtml = `<p>Approval withdrawn by ${esc(post.a_by)}. Saving that to the post folder now.</p>`;
  else if (post.status === 'approval_failed') approveHtml = `<p style="color:var(--bad)">The approval could not be saved: ${esc(post.a_msg || 'unknown reason')}</p>`;
  if (canApprove && future && post.video_key) {
    if (approvedInFile && post.status !== 'approving') {
      approveHtml += `<button class="btn ghost" id="unapprove">Withdraw approval</button>`;
    } else if (post.status !== 'approving') {
      approveHtml += `<button class="btn gold" id="approve">Approve this cut for ${esc(dayLabel(post.post_date))}</button>`;
    }
  } else if (!canApprove && future && post.status === 'review') {
    approveHtml += `<p class="muted">Only the owner or a manager can approve. Leave a note if something needs changing.</p>`;
  }

  const tabs = [
    ['hook', 'Hook and title'],
    ['script', 'Script'],
    ['caption', 'Caption'],
    ['settings', 'Settings'],
    ['notes', `Notes${notes.length ? ` (${notes.length})` : ''}`],
  ];
  $app.innerHTML = `
    <a class="back" href="#/">← Plan</a>
    <div class="label">${post.post_date ? `${esc(dayLabel(post.post_date))}, ${fmtTime(channel.post_time)}` : 'Parked, no date'}</div>
    <h1>${esc(post.title || post.slug)}</h1>
    <div class="post-grid">
      <div class="media">
        ${post.video_key
          ? `<video controls playsinline preload="metadata" ${post.cover_key ? `poster="${mediaUrl(post.cover_key)}"` : ''} src="${mediaUrl(post.video_key)}"></video>`
          : `<div class="novideo">No video yet for this post.</div>`}
        <div class="meta">${post.video_bytes ? `${(post.video_bytes / 1048576).toFixed(1)} MB · ` : ''}${esc(post.folder)}</div>
        <div class="approve-box">
          <div class="row" style="display:flex;gap:8px;align-items:center;margin-bottom:10px">${chip(post.status)}</div>
          <ul class="checks">${post.checks.map((c) => `<li class="${c.ok ? 'ok' : 'no'}">${esc(c.label)}</li>`).join('')}</ul>
          ${failing.length && canApprove && future && !approvedInFile ? `<p class="muted" style="font-size:13px">Some checks need a look before you approve.</p>` : ''}
          ${approveHtml}
          ${post.first_line ? `<div class="final">Post folder says: ${esc(post.first_line.slice(0, 240))}${post.first_line.length > 240 ? '…' : ''}</div>` : ''}
        </div>
      </div>
      <div>
        <div class="sec-tabs" role="tablist">${tabs.map(([k, l], i) => `<button role="tab" data-k="${k}" class="${i ? '' : 'on'}">${esc(l)}</button>`).join('')}</div>
        <div id="sec"></div>
      </div>
    </div>`;

  const sections = {
    hook: () => `<div class="panel">
        <div class="label">Hook (first words of the video)</div>
        <div class="big-hook">${esc(post.hook || 'Not found in the post folder')}</div>
        <div class="label">Title</div><p>${esc(post.title || '—')}</p></div>`,
    script: () => {
      const beatList = beats.length
        ? `<div class="label">On-screen beats (${beats.length})</div><ol class="beats">${beats
            .map((b) => `<li>${esc(b.text)}${b.img ? `<div class="img">Picture: ${esc(b.img)}</div>` : ''}</li>`)
            .join('')}</ol>`
        : '';
      const structure = post.structure ? `<div class="label">Structure</div>${md(post.structure)}` : '';
      return `<div class="panel">${structure || beatList ? structure + beatList : '<p class="muted">No script found in the post folder yet.</p>'}</div>`;
    },
    caption: () => `<div class="panel"><button class="copy" data-copy="desc">Copy</button>
        <div class="label">Description and Instagram caption</div><pre class="caption" id="desc">${esc(post.description || '—')}</pre></div>`,
    settings: () => `<div class="panel">${post.settings ? md(post.settings) : '<p class="muted">No settings listed.</p>'}</div>`,
    notes: () => `<div class="panel">
        ${notes.length ? notes.map((n) => `<div class="note"><div class="who">${esc(n.name || n.email)} · ${esc(ago(n.at))}</div><div>${esc(n.text)}</div></div>`).join('') : '<p class="muted">No notes yet.</p>'}
        ${canNote ? `<div class="form-row"><textarea id="note" placeholder="What should change? For example: the hook is too long, image 6 should show both brothers."></textarea><button class="btn" id="addnote">Add note</button></div>` : ''}
        ${events.length ? `<div class="label" style="margin-top:18px">History</div>${events.map((e) => `<div class="muted" style="font-size:13px">${esc(ago(e.at))} · ${esc(e.email)} · ${esc(e.kind.replace(/_/g, ' '))}${e.detail ? `: ${esc(e.detail)}` : ''}</div>`).join('')}` : ''}
      </div>`,
  };
  const $sec = document.getElementById('sec');
  const open = (k) => {
    document.querySelectorAll('.sec-tabs button').forEach((b) => b.classList.toggle('on', b.dataset.k === k));
    $sec.innerHTML = sections[k]();
    const copy = $sec.querySelector('[data-copy]');
    if (copy) copy.onclick = async () => {
      try { await navigator.clipboard.writeText(post.description || ''); toast('Caption copied'); } catch { toast('Could not copy'); }
    };
    const add = document.getElementById('addnote');
    if (add) add.onclick = async () => {
      const text = document.getElementById('note').value.trim();
      if (!text) return;
      add.disabled = true;
      try {
        await api(`/api/channels/${encodeURIComponent(state.channelId)}/posts/${encodeURIComponent(folder)}/notes`, { method: 'POST', body: JSON.stringify({ text }) });
        toast('Note added');
        showPost(folder).then(() => document.querySelector('[data-k="notes"]').click());
      } catch (e) { toast(e.message); add.disabled = false; }
    };
  };
  document.querySelectorAll('.sec-tabs button').forEach((b) => (b.onclick = () => open(b.dataset.k)));
  open('hook');

  const approve = document.getElementById('approve');
  if (approve) approve.onclick = async () => {
    const warn = failing.length ? `\n\nChecks needing a look:\n- ${failing.map((c) => c.label).join('\n- ')}` : '';
    if (!confirm(`Approve "${post.title || post.slug}" to post on ${dayLabel(post.post_date)} at ${fmtTime(channel.post_time)}?${warn}`)) return;
    approve.disabled = true;
    try {
      await api(`/api/channels/${encodeURIComponent(state.channelId)}/posts/${encodeURIComponent(folder)}/approve`, { method: 'POST', body: JSON.stringify({ video_sha: post.video_sha }) });
      toast('Approved. It will be saved to the post folder within 15 minutes.');
      showPost(folder);
    } catch (e) { toast(e.message); approve.disabled = false; }
  };
  const un = document.getElementById('unapprove');
  if (un) un.onclick = async () => {
    if (!confirm('Withdraw the approval? The post will not go out until someone approves it again.')) return;
    un.disabled = true;
    try {
      await api(`/api/channels/${encodeURIComponent(state.channelId)}/posts/${encodeURIComponent(folder)}/unapprove`, { method: 'POST', body: '{}' });
      toast('Approval withdrawn');
      showPost(folder);
    } catch (e) { toast(e.message); un.disabled = false; }
  };
}

// ------------------------------------------------------------ team
async function showTeam() {
  setTab('team');
  let data;
  try { data = await api(`/api/channels/${encodeURIComponent(state.channelId)}/members`); } catch (e) { return fail(e); }
  const owner = data.me.role === 'owner';
  $app.innerHTML = `
    <h1>Team</h1>
    <p class="sync">People sign in with their Google account. Only emails on this list can open the Studio.</p>
    <div class="panel">${data.members
      .map((m) => `<div class="member"><div><div>${esc(m.name || m.email)}</div><div class="em">${esc(m.email)}</div><div class="em">${esc(ROLE_HELP[m.role])}</div></div>
        <div style="text-align:right"><div class="role">${esc(m.role)}</div>${owner && m.role !== 'owner' ? `<button class="linkbtn" data-rm="${esc(m.email)}">Remove</button>` : ''}</div></div>`)
      .join('')}</div>
    ${owner ? `<h2>Invite someone</h2><div class="panel">
      <div class="form-row three">
        <input id="m-email" type="email" placeholder="Their Google email" autocomplete="off">
        <input id="m-name" placeholder="Name">
        <select id="m-role" class="inp"><option value="editor">Editor</option><option value="manager">Manager</option><option value="viewer">Viewer</option></select>
      </div>
      <p class="muted" style="font-size:13px">Manager: can approve posts. Editor: can review and leave notes. Viewer: look only.</p>
      <button class="btn gold" id="m-add">Add to the team</button>
      <p class="muted" style="font-size:13px">Then send them the Studio link. They sign in with that Google account.</p></div>` : ''}`;
  if (!owner) return;
  document.getElementById('m-add').onclick = async () => {
    const body = { email: document.getElementById('m-email').value, name: document.getElementById('m-name').value, role: document.getElementById('m-role').value };
    try {
      await api(`/api/channels/${encodeURIComponent(state.channelId)}/members`, { method: 'POST', body: JSON.stringify(body) });
      toast('Added');
      showTeam();
    } catch (e) { toast(e.message); }
  };
  document.querySelectorAll('[data-rm]').forEach((b) => (b.onclick = async () => {
    if (!confirm(`Remove ${b.dataset.rm} from the team?`)) return;
    try {
      await api(`/api/channels/${encodeURIComponent(state.channelId)}/members/${encodeURIComponent(b.dataset.rm)}`, { method: 'DELETE' });
      toast('Removed');
      showTeam();
    } catch (e) { toast(e.message); }
  }));
}

function fail(e) {
  $app.innerHTML = `<div class="empty"><p>${esc(e.message)}</p><p><a href="#/">Back to the plan</a></p></div>`;
}

boot();
