#!/bin/zsh
# Claude Watcher installer — generator on a 60s launchd timer (+ optional SwiftBar).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${CW_OUT:-$HOME/.claude-watcher}"
LABEL="com.$(whoami).claude-watcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$OUT" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$DIR/watch-status.py</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>CW_OUT</key><string>$OUT</string>
    <key>CW_RELAY_DIR</key><string>${CW_RELAY_DIR:-}</string>
  </dict>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>$OUT/watcher.err.log</string>
</dict></plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
/usr/bin/python3 "$DIR/watch-status.py"

echo "✓ generator loaded ($LABEL, every 60s)"
echo "✓ dashboard: open \"$OUT/index.html\"  (bookmark it — it refreshes itself)"
echo
echo "Menu bar (optional):"
echo "  brew install --cask swiftbar"
echo "  defaults write com.ameba.SwiftBar PluginDirectory \"$DIR/swiftbar\""
echo "  open -a SwiftBar"
echo
echo "VERIFY (never trust an installer): the dashboard must show the session"
echo "that ran this — grep your own command in it. If it can't see the session"
echo "that built it, it can't see anything."
