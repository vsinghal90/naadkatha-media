#!/usr/bin/env python3
"""Naad Katha Air sync: uploads new media from the MacBook Air to the private
Hugging Face dataset naadkatha/air-inbox, so Claude threads can pull them.
Runs every minute from launchd. Never moves, renames or deletes local files."""
import json, os, subprocess, sys, time, datetime, fcntl
from pathlib import Path

HOME = Path.home()
BASE = HOME / ".naadkatha-air"
STATE = BASE / "state.json"
LOG = BASE / "sync.log"
REPO = os.environ.get("NK_REPO", "naadkatha/air-inbox")
WATCH = {
    "downloads": HOME / "Downloads",
    "claudes-folder": HOME / "Desktop" / "Claude's Folder",   # includes NaadKatha/ and NaadKatha/Music/
}
EXT = {".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".m4a"}
ALWAYS_PREFIX = ("nk_",)          # our own files: sent even if older than install
MAX_BYTES = 500 * 1024 * 1024
SETTLE_S = 20                      # skip files still being written


def log(msg):
    BASE.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def token():
    return subprocess.run(["security", "find-generic-password", "-s", "naadkatha-hf", "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()


def main():
    BASE.mkdir(exist_ok=True)
    lock = open(BASE / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    since = state.setdefault("since", time.time())
    done = state.setdefault("done", {})
    now = time.time()
    todo = []
    for src, d in WATCH.items():
        if not d.is_dir():
            continue
        try:
            entries = [q for q in d.rglob("*") if len(q.relative_to(d).parts) <= 3
                       and not any(part.startswith(".") for part in q.relative_to(d).parts)]
        except PermissionError as e:
            log(f"no access to {d}: {e} (allow python3 in System Preferences > Security > Files and Folders)")
            continue
        for p in entries:
            if not p.is_file() or p.suffix.lower() not in EXT or p.name.startswith("."):
                continue
            st = p.stat()
            if now - st.st_mtime < SETTLE_S or st.st_size == 0 or st.st_size > MAX_BYTES:
                continue
            if st.st_mtime < since and not p.name.lower().startswith(ALWAYS_PREFIX):
                continue
            rel = p.relative_to(d).as_posix()
            key = f"{src}/{rel}|{st.st_size}|{int(st.st_mtime)}"
            if key in done:
                continue
            todo.append((src, p, st, key))
    if not todo:
        STATE.write_text(json.dumps(state))
        return
    from huggingface_hub import HfApi
    api = HfApi(token=token())
    if not state.get("repo_ok"):
        api.create_repo(REPO, repo_type="dataset", private=True, exist_ok=True)
        state["repo_ok"] = True
    for src, p, st, key in todo:
        day = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        dest = f"{day}/{src}/{p.relative_to(WATCH[src]).as_posix()}"
        try:
            api.upload_file(path_or_fileobj=str(p), path_in_repo=dest, repo_id=REPO,
                            repo_type="dataset", commit_message=f"air: {dest}")
            done[key] = dest
            log(f"sent {dest} ({st.st_size} bytes)")
        except Exception as e:
            log(f"FAILED {dest}: {e}")
        STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR {e}")
        sys.exit(1)
