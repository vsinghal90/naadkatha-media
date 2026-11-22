#!/bin/bash
# One-time installer for the Naad Katha Air sync. Run in Terminal on the MacBook Air:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/vsinghal90/naadkatha-media/claude/project-thread-59bzg3/tools/air-sync/install.sh)"
set -e
RAW="https://raw.githubusercontent.com/vsinghal90/naadkatha-media/claude/project-thread-59bzg3/tools/air-sync"
B="$HOME/.naadkatha-air"
mkdir -p "$B"
echo "1/4 Getting the sync script..."
curl -fsSL "$RAW/air_sync.py" -o "$B/air_sync.py"
echo "2/4 Setting up Python (takes a minute)..."
/usr/bin/python3 -m venv "$B/venv"
"$B/venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
"$B/venv/bin/pip" install -q "huggingface_hub"
echo "3/4 Paste your Hugging Face WRITE token (it will not show) and press Return:"
read -rs TOK < /dev/tty
echo
security delete-generic-password -s naadkatha-hf >/dev/null 2>&1 || true
security add-generic-password -s naadkatha-hf -a air -w "$TOK"
unset TOK
echo "4/4 Starting the every-minute sync..."
PL="$HOME/Library/LaunchAgents/com.naadkatha.airsync.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.naadkatha.airsync</string>
<key>ProgramArguments</key><array><string>$B/venv/bin/python</string><string>$B/air_sync.py</string></array>
<key>StartInterval</key><integer>60</integer>
<key>RunAtLoad</key><true/>
<key>StandardErrorPath</key><string>$B/launchd.err</string>
</dict></plist>
PLIST
launchctl unload "$PL" >/dev/null 2>&1 || true
launchctl load "$PL"
sleep 8
echo
echo "Done. If macOS asks whether python can access Downloads or Desktop, click OK."
echo "Log: $B/sync.log"
tail -5 "$B/sync.log" 2>/dev/null || true
