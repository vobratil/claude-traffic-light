# Claude Traffic Light

A GNOME system tray indicator that shows the current status of a [Claude Code](https://claude.ai/code) session as a colour-coded traffic light icon.

## States

| Icon | State | Meaning |
|------|-------|---------|
| Grey (dim) | **Idle** | Claude Code is not running |
| Green | **Ready** | Claude finished — waiting for your next prompt |
| Orange | **Working** | Claude is actively processing |
| Red | **Waiting** | Claude needs your input (permission prompt or question) |

The icon polls every second and switches automatically as your session progresses.

## Requirements

- Fedora / GNOME (tested on Fedora 44 with GNOME Shell)
- [`appindicatorsupport@rgcjonas.gmail.com`](https://extensions.gnome.org/extension/615/appindicator-support/) GNOME extension — **installed and enabled**
- Python 3 with `gi` (PyGObject), `AppIndicator3 0.1`, `Gtk 3.0`, `cairo`
- Claude Code CLI (`claude` binary on PATH)

Install the Python dependencies on Fedora:

```bash
sudo dnf install python3-gobject libappindicator-gtk3 python3-cairo
```

Enable the AppIndicator extension if it isn't already:

```bash
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

## Installation

```bash
git clone <repo-url> ai-traffic-light
cd ai-traffic-light
bash install.sh
```

The installer:

1. Copies `claude_traffic_light.py` to `~/.local/bin/claude-traffic-light`
2. Copies the two hook scripts to `~/.local/bin/`
3. Creates an autostart desktop entry so the indicator launches on login
4. Injects the required hooks into `~/.claude/settings.json`

Start it immediately (without logging out):

```bash
~/.local/bin/claude-traffic-light &
```

## How it works

### State file

The indicator reads `~/.local/share/claude-traffic-light/status` once per second. The file contains one of:

| Value | Meaning |
|-------|---------|
| `ready` | Claude finished a response |
| `working` | Claude is running (default while Claude process is alive and no other state is set) |
| `waiting` | Claude needs user input |

If the file is absent or Claude's process is not detected, the indicator shows **idle**.

### Claude Code hooks

Two hooks in `~/.claude/settings.json` keep the state file up to date:

- **Stop hook** (`claude-tl-stop`) — fires when Claude finishes a response; writes `ready`.
- **Notification hook** (`claude-tl-notify`) — fires for permission requests and completion alerts. Only writes `waiting` if the current state is not already `ready` (so a completion notification doesn't override the green light).

### Process detection

`pgrep -x claude` detects whether the Claude Code binary is running. When no Claude process is found the indicator shows **idle** regardless of the state file.

### Single-instance enforcement

A lock file (`~/.local/share/claude-traffic-light/instance.lock`) is held with `flock`. A second launch prints an error and exits immediately.

## File layout

```
~/.local/bin/
  claude-traffic-light        # main indicator script
  claude-tl-stop              # Stop hook
  claude-tl-notify            # Notification hook

~/.local/share/claude-traffic-light/
  status                      # current state (ready | working | waiting)
  instance.lock               # single-instance lock
  icons/hicolor/22x22/apps/   # generated PNG icons (22×22 px)
  icons/hicolor/index.theme   # required for GTK icon lookup

~/.config/autostart/
  claude-traffic-light.desktop  # autostart entry
```

## Troubleshooting

**No icon appears in the tray**

- Confirm the AppIndicator extension is enabled: `gnome-extensions list --enabled | grep appindicator`
- Check for a stale lock file: `cat ~/.local/share/claude-traffic-light/instance.lock` — kill that PID if it's dead, then delete the lock file.

**Icon shows a three-dot placeholder**

- The `index.theme` file is missing or the icon directory structure is wrong. Re-run `install.sh` or start the indicator fresh — it regenerates the theme on startup.

**State never changes from idle**

- Confirm `claude` is on your PATH: `which claude`
- Check that the hooks were injected: `grep claude-tl ~/.claude/settings.json`
