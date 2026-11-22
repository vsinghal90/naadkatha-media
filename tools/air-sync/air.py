#!/usr/bin/env python3
"""Container side of the Air sync. Lists and pulls files the MacBook Air sent to
the private HF dataset naadkatha/air-inbox (the proxy adds the HF login).
  python3 air.py list [words...]            newest first, filter by words
  python3 air.py get <words...> --to DIR     copy matching files into DIR
"""
import json, sys, os, urllib.request, urllib.parse
REPO = os.environ.get("NK_REPO", "naadkatha/air-inbox")
API = f"https://huggingface.co/api/datasets/{REPO}"

def files():
    out, url = [], f"{API}/tree/main?recursive=true&expand=true"
    while url:
        r = urllib.request.urlopen(url, timeout=60)
        out += [f for f in json.load(r) if f.get("type") == "file"]
        link = r.headers.get("Link", "")
        url = link.split(";")[0].strip("<> ") if 'rel="next"' in link else None
    for f in out:
        f["time"] = (f.get("lastCommit") or {}).get("date", "")
    return sorted(out, key=lambda f: f["time"], reverse=True)

def match(f, words):
    return all(w.lower() in f["path"].lower() for w in words)

def main(a):
    if not a or a[0] not in ("list", "get"):
        print(__doc__); return
    cmd, rest = a[0], a[1:]
    to = None
    if "--to" in rest:
        i = rest.index("--to"); to = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
    sel = [f for f in files() if match(f, rest)]
    if cmd == "list":
        for f in sel:
            print(f'{f["time"][:16]}  {f["size"]/1e6:7.1f} MB  {f["path"]}')
        print(f"{len(sel)} file(s)"); return
    if not to or not sel:
        sys.exit("need --to DIR and at least one match")
    os.makedirs(to, exist_ok=True)
    for f in sel:
        dest = os.path.join(to, os.path.basename(f["path"]))
        if os.path.exists(dest) and os.path.getsize(dest) == f["size"]:
            print("have", dest); continue
        u = f"https://huggingface.co/datasets/{REPO}/resolve/main/" + urllib.parse.quote(f["path"])
        with urllib.request.urlopen(u, timeout=600) as r, open(dest + ".part", "wb") as o:
            while chunk := r.read(1 << 20):
                o.write(chunk)
        os.replace(dest + ".part", dest)
        print("got", dest, f'{f["size"]/1e6:.1f} MB')

if __name__ == "__main__":
    main(sys.argv[1:])
