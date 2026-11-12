#!/usr/bin/env python3
"""Naad Katha Studio sync.

Runs inside the Claude project (scheduled every 15 minutes). It:
  1. reads every post folder  <slug>_<DDMMYY>/  (needs an upload-text.md),
  2. uploads new or changed videos and covers to the Studio's private storage,
  3. sends titles, hooks, captions, scripts and status to the Studio,
  4. writes approvals made in the Studio into upload-text.md as the
     "FINAL CUT." first line that the auto-posting pipeline reads.

Usage:
  STUDIO_URL=https://studio.example.com STUDIO_SYNC_TOKEN=... \
  python3 sync.py --root /mnt/project-files/naad-katha-posts [--channel naad-katha] [--dry-run]

When the Studio sits behind Cloudflare Access, also set
CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET (an Access service token).
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
FOLDER_RE = re.compile(r"^(?P<slug>.+)_(?P<d>\d{2})(?P<m>\d{2})(?P<y>\d{2})$")
PARKED_RE = re.compile(r"^(?P<slug>.+)_parked$")


# ---------------------------------------------------------------- HTTP

class Studio:
    def __init__(self, base: str, token: str, channel: str, dry: bool = False):
        self.base = base.rstrip("/")
        self.token = token
        self.channel = channel
        self.dry = dry

    def _req(self, method, path, body=None, ctype="application/json", data_stream=None, length=None):
        url = f"{self.base}/api/sync/{urllib.parse.quote(self.channel)}{path}"
        headers = {"Authorization": f"Bearer {self.token}", "User-Agent": "naadkatha-studio-sync/1"}
        cid, csec = os.environ.get("CF_ACCESS_CLIENT_ID"), os.environ.get("CF_ACCESS_CLIENT_SECRET")
        if cid and csec:
            headers["CF-Access-Client-Id"] = cid
            headers["CF-Access-Client-Secret"] = csec
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = ctype
        elif data_stream is not None:
            data = data_stream
            headers["Content-Type"] = ctype
            headers["Content-Length"] = str(length)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Studio {method} {path} failed: {e.code} {e.read()[:300]!r}")

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, body):
        if self.dry:
            print(f"[dry-run] POST {path} ({len(json.dumps(body))} bytes)")
            return {}
        return self._req("POST", path, body=body)

    def put_file(self, key, file: Path, sha: str, ctype: str):
        if self.dry:
            print(f"[dry-run] PUT {key} ({file.stat().st_size} bytes)")
            return
        q = urllib.parse.quote(key) + "?sha=" + sha
        with open(file, "rb") as fh:
            self._req("PUT", f"/media/{q}", data_stream=fh, ctype=ctype, length=file.stat().st_size)

    def delete(self, key):
        if self.dry:
            print(f"[dry-run] DELETE {key}")
            return
        self._req("DELETE", f"/media/{urllib.parse.quote(key)}")


# ---------------------------------------------------------------- reading folders

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def sections(text: str) -> dict[str, str]:
    """Split upload-text.md into {heading_lower: body} on '## ' headings."""
    out, cur, buf = {}, "_top", []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1).strip().lower(), []
        else:
            buf.append(line)
    out[cur] = "\n".join(buf).strip()
    return out


def pick(secs: dict[str, str], *names: str) -> str | None:
    for name in names:
        for k, v in secs.items():
            if k.startswith(name):
                return v
    return None


def find_hook(secs, beats) -> str | None:
    structure = pick(secs, "structure", "script") or ""
    m = re.search(r"Hook[^:]*:\s*\"([^\"]+)\"", structure)
    if m:
        return m.group(1).strip()
    log = pick(secs, "log line")
    if log:
        for row in csv.reader(io.StringIO(log.strip().splitlines()[0])):
            if len(row) > 7 and row[7].strip():
                return row[7].strip()
    if beats:
        return beats[0]["text"]
    return None


def read_beats(folder: Path):
    f = folder / "build" / "beats.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    beats = []
    for b in data if isinstance(data, list) else []:
        if not isinstance(b, dict):
            continue
        parts = []
        if b.get("top"):
            parts.append(strip_tags(b["top"]))
        for c in b.get("cap") or []:
            if isinstance(c, str) and c.strip() and c.strip() != "x":
                parts.append(strip_tags(c))
        text = " ".join(p for p in parts if p)
        if text:
            beats.append({"text": text[:600], "img": b.get("img")})
    return beats or None


def find_video(folder: Path) -> Path | None:
    own = folder / f"{folder.name}.mp4"
    if own.exists():
        return own
    mp4s = sorted(folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp4s[0] if mp4s else None


def find_cover(folder: Path) -> Path | None:
    for pat in ("*-cover_*.jpg", "*-cover_*.png", "*cover*.jpg", "*cover*.png"):
        hits = sorted(folder.glob(pat))
        if hits:
            return hits[0]
    return None


def read_folder(folder: Path):
    up = folder / "upload-text.md"
    if not up.exists():
        return None
    m, p = FOLDER_RE.match(folder.name), PARKED_RE.match(folder.name)
    if m:
        slug = m.group("slug")
        post_date = f"20{m.group('y')}-{m.group('m')}-{m.group('d')}"
    elif p:
        slug, post_date = p.group("slug"), None
    else:
        return None
    text = up.read_text(encoding="utf-8", errors="replace")
    first_line = text.splitlines()[0].strip() if text.strip() else ""
    secs = sections(text)
    beats = read_beats(folder)
    title = (pick(secs, "title") or "").strip().splitlines()
    return {
        "folder": folder.name,
        "slug": slug,
        "post_date": post_date,
        "first_line": first_line,
        "title": title[0].strip() if title else None,
        "hook": find_hook(secs, beats),
        "description": pick(secs, "description", "caption"),
        "settings": "\n\n".join(x for x in [pick(secs, "settings"), ("Tags: " + pick(secs, "tags")) if pick(secs, "tags") else None] if x) or None,
        "structure": pick(secs, "structure", "script"),
        "beats": beats,
        "folder_mtime": dt.datetime.fromtimestamp(up.stat().st_mtime, IST).isoformat(),
    }


# ---------------------------------------------------------------- approvals

def write_approval(folder: Path, a: dict) -> tuple[bool, str, str | None]:
    up = folder / "upload-text.md"
    if not up.exists():
        return False, "upload-text.md is missing", None
    when = dt.datetime.fromisoformat(a["at"].replace("Z", "+00:00")).astimezone(IST)
    stamp = when.strftime("%-d %b %Y, %-I:%M %p IST").replace("AM", "am").replace("PM", "pm")
    who = a.get("by_name") or a["by_email"]
    if a["state"] == "approved":
        video = find_video(folder)
        if not video:
            return False, "the video file is missing", None
        if a.get("video_sha") and sha256(video) != a["video_sha"]:
            return False, "the video changed after it was approved; please review the new cut", None
        if a["role"] == "owner":
            new = f"FINAL CUT. Owner approved {stamp} in Studio ({who})."
        else:
            new = f"FINAL CUT. Approved by {who} ({a['role']}) {stamp} in Studio."
    else:
        new = f"NOT APPROVED. Approval withdrawn by {who} {stamp} in Studio."

    text = up.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    old = lines[0].strip() if lines else ""
    backup_dir = folder / ".studio-backups"
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(up, backup_dir / f"upload-text_{dt.datetime.now(IST):%Y%m%d-%H%M%S}.md")
    rest = lines[1:] if lines else []
    keep = [] if (not old or old.startswith(("FINAL CUT.", "NOT APPROVED.", "Earlier status:"))) else [f"Earlier status: {old}"]
    # Drop an older "Earlier status:" line right under the first line so they don't pile up.
    if rest and rest[0].startswith("Earlier status:") and keep:
        rest = rest[1:]
    up.write_text("\n".join([new, *keep, *rest]) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return True, new, new


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/mnt/project-files/naad-katha-posts")
    ap.add_argument("--channel", default="naad-katha")
    ap.add_argument("--url", default=os.environ.get("STUDIO_URL"))
    ap.add_argument("--token", default=os.environ.get("STUDIO_SYNC_TOKEN"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-media", action="store_true", help="metadata only, no video uploads")
    args = ap.parse_args()
    if not args.url or not args.token:
        sys.exit("Set STUDIO_URL and STUDIO_SYNC_TOKEN (or --url/--token).")
    studio = Studio(args.url, args.token, args.channel, args.dry_run)
    root = Path(args.root)

    # 1. Write approvals first, so the folder state we send next is current.
    pending = studio.get("/approvals").get("approvals", [])
    for a in pending:
        folder = root / a["folder"]
        if args.dry_run:
            print(f"[dry-run] would write {a['state']} for {a['folder']}")
            continue
        ok, msg, first = write_approval(folder, a)
        studio.post(f"/approvals/{urllib.parse.quote(a['folder'])}/ack", {"ok": ok, "msg": msg, "first_line": first})
        print(("wrote " if ok else "FAILED ") + f"{a['folder']}: {msg}")

    # 2. Read folders, upload media that changed.
    index = {} if args.skip_media else studio.get("/media-index").get("keys", {})
    wanted_keys: set[str] = set()
    posts = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        info = read_folder(folder)
        if not info:
            continue
        for kind, path, ctype in (
            ("video", find_video(folder), "video/mp4"),
            ("cover", find_cover(folder), "image/png" if str(find_cover(folder)).endswith(".png") else "image/jpeg"),
        ):
            if not path:
                continue
            sha = sha256(path)
            key = f"{folder.name}/{sha[:10]}-{path.name}"
            info[f"{kind}_key"] = key
            if kind == "video":
                info["video_sha"] = sha
                info["video_bytes"] = path.stat().st_size
            wanted_keys.add(key)
            if not args.skip_media and index.get(key) != sha:
                print(f"upload {key} ({path.stat().st_size // 1024} KB)")
                studio.put_file(key, path, sha, ctype)
        posts.append(info)

    # 3. Remove media of old versions.
    if not args.skip_media:
        for key in index:
            if key not in wanted_keys:
                print(f"delete old {key}")
                studio.delete(key)

    res = studio.post("/posts", {"posts": posts, "full": True})
    print(f"synced {len(posts)} posts, {len(pending)} approvals handled", res)


if __name__ == "__main__":
    main()
