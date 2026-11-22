# Air sync (Naad Katha)
New media saved on the MacBook Air (Gemini clips in ~/Downloads, Flow clips in ~/Desktop/Claude's Folder/NaadKatha) is uploaded every minute to the PRIVATE Hugging Face dataset `naadkatha/air-inbox`, under `<date>/<downloads|flow>/<name>`. Only media files (mp4, mov, webm, png, jpg, webp, wav, mp3, m4a) made after install, plus any `nk_*` file. Local files are never moved or deleted.
- Install on the Air (once): `bash -c "$(curl -fsSL https://raw.githubusercontent.com/vsinghal90/naadkatha-media/claude/project-thread-59bzg3/tools/air-sync/install.sh)"` then paste a Hugging Face WRITE token. The token is kept in the Mac keychain, never in this repo.
- Stop: run uninstall.sh.
- Pull in a Claude container: `python3 air.py list ravan` and `python3 air.py get ravan score --to /mnt/project-files/...`
