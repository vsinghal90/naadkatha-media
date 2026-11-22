#!/bin/bash
launchctl unload "$HOME/Library/LaunchAgents/com.naadkatha.airsync.plist" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/com.naadkatha.airsync.plist"
security delete-generic-password -s naadkatha-hf >/dev/null 2>&1
echo "Air sync stopped. Your files were never touched; ~/.naadkatha-air can be deleted."
