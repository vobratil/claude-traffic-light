#!/bin/bash
# install.sh — install Claude Traffic Light indicator

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing Claude Traffic Light..."

# ── binaries ─────────────────────────────────────────────────────────────────
mkdir -p "$HOME/.local/bin"
install -m 755 "$REPO/claude_traffic_light.py" "$HOME/.local/bin/claude-traffic-light"
install -m 755 "$REPO/hooks/claude-tl-stop"   "$HOME/.local/bin/claude-tl-stop"
install -m 755 "$REPO/hooks/claude-tl-notify" "$HOME/.local/bin/claude-tl-notify"

# ── data directory ────────────────────────────────────────────────────────────
mkdir -p "$HOME/.local/share/claude-traffic-light/icons"

# ── autostart desktop entry ───────────────────────────────────────────────────
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/claude-traffic-light.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Claude Traffic Light
Comment=System tray indicator for Claude Code status
Exec=$HOME/.local/bin/claude-traffic-light
Icon=preferences-system
Hidden=false
X-GNOME-Autostart-enabled=true
EOF

# ── Claude Code hooks ─────────────────────────────────────────────────────────
SETTINGS="$HOME/.claude/settings.json"

if [ ! -f "$SETTINGS" ]; then
    echo "WARNING: $SETTINGS not found — skipping hook injection."
    echo "         Add hooks manually following README instructions."
else
    python3 - "$SETTINGS" << 'PYEOF'
import sys, json, pathlib

path = pathlib.Path(sys.argv[1])
cfg = json.loads(path.read_text())

hooks = cfg.setdefault('hooks', {})

# Stop hook
stop_hooks = hooks.setdefault('Stop', [])
stop_cmd = 'printf ready > "$HOME/.local/share/claude-traffic-light/status"'
if not any(
    any(h.get('command') == stop_cmd for h in entry.get('hooks', []))
    for entry in stop_hooks
):
    stop_hooks.append({'hooks': [{'type': 'command', 'command': stop_cmd}]})

# Notification hook
notify_hooks = hooks.setdefault('Notification', [])
notify_cmd = '$HOME/.local/bin/claude-tl-notify'
if not any(
    any(h.get('command') == notify_cmd for h in entry.get('hooks', []))
    for entry in notify_hooks
):
    notify_hooks.append({'hooks': [{'type': 'command', 'command': notify_cmd}]})

path.write_text(json.dumps(cfg, indent=2) + '\n')
print("Hooks written to", path)
PYEOF
fi

echo ""
echo "Done! Next steps:"
echo ""
echo "  1. Start the indicator now:   ~/.local/bin/claude-traffic-light &"
echo "     (it will auto-start on the next login)"
echo ""
echo "  2. The indicator reads state from:"
echo "     ~/.local/share/claude-traffic-light/status"
echo "     Values: ready | waiting | error  (absent/idle = Claude not running)"
