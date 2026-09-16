#!/usr/bin/env python3
"""Claude Code status traffic light — GNOME system tray indicator."""

import math
import os
import subprocess
import sys

import ctypes
import ctypes.util

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')

from gi.repository import AppIndicator3, Gtk, GLib
import cairo

# AppIndicator3 calls gtk_widget_get_scale_factor before the StatusNotifier
# widget is realized; suppress that single known-harmless Gtk-CRITICAL.
def _suppress_scale_factor_warning():
    try:
        _lib = ctypes.CDLL(ctypes.util.find_library('glib-2.0'))
        _GLogFunc = ctypes.CFUNCTYPE(
            None,
            ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p, ctypes.c_void_p,
        )

        @_GLogFunc
        def _handler(domain, level, message, data):
            if message and b'gtk_widget_get_scale_factor' in message:
                return
            sys.stderr.write(
                f"({domain.decode() if domain else ''}): {message.decode() if message else ''}\n"
            )

        _lib.g_log_set_handler(b'Gtk', ctypes.c_uint(1 << 3), _handler, None)
        # Keep reference alive for the process lifetime
        _suppress_scale_factor_warning._handler = _handler
    except Exception:
        pass

_suppress_scale_factor_warning()

DATA_DIR      = os.path.expanduser('~/.local/share/claude-traffic-light')
STATE_FILE    = os.path.join(DATA_DIR, 'status')
LOCK_FILE     = os.path.join(DATA_DIR, 'instance.lock')
# AppIndicator3 set_icon_theme_path points to the root of a hicolor-style tree.
# GNOME Shell's AppIndicator extension prepends this to GTK's theme search path
# and then requests icons at the panel icon size (22 px).
ICON_THEME_DIR = os.path.join(DATA_DIR, 'icons')
ICON_DIR       = os.path.join(ICON_THEME_DIR, 'hicolor', '22x22', 'apps')
POLL_MS        = 1000  # state polling interval

TOOLTIPS = {
    'idle':    'Claude: not running',
    'ready':   'Claude: ready',
    'working': 'Claude: working',
    'waiting': 'Claude: needs your input',
}


# ── icon drawing ────────────────────────────────────────────────────────────

def _rounded_rect(ctx, x, y, w, h, r):
    ctx.arc(x + r,     y + r,     r,  math.pi,      3 * math.pi / 2)
    ctx.arc(x + w - r, y + r,     r,  3*math.pi/2,  0)
    ctx.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
    ctx.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
    ctx.close_path()


def _icon_name(state: str) -> str:
    return f'claude-tl-{state}'


def draw_icon(state: str, h: int = 22) -> str:
    """Render a horizontal traffic-light PNG for *state*, return the icon name.

    Layout: three lights side by side, each filling the full icon height.
    Canvas is 3×h wide so every bulb gets roughly h×h of space.
    """
    w = h * 3
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)

    ctx.set_operator(cairo.OPERATOR_CLEAR)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    # Housing
    margin, corner = 1, 3
    if state == 'idle':
        ctx.set_source_rgba(0.30, 0.30, 0.30, 0.50)
    else:
        ctx.set_source_rgba(0.12, 0.12, 0.12, 0.95)
    _rounded_rect(ctx, margin, margin, w - 2*margin, h - 2*margin, corner)
    ctx.fill()

    # Lights: red left, orange centre, green right
    lr  = (h - 4) / 2          # radius: fills height minus a 1 px border each side
    cy  = h / 2
    # evenly space the three centres across the width
    lights = [
        (w / 6,     cy, 'red'),
        (w / 2,     cy, 'orange'),
        (w * 5 / 6, cy, 'green'),
    ]

    on_rgb  = {'red': (1.00, 0.15, 0.10), 'orange': (1.00, 0.55, 0.00), 'green': (0.15, 0.95, 0.15)}
    off_rgb = {'red': (0.32, 0.05, 0.05), 'orange': (0.32, 0.18, 0.00), 'green': (0.05, 0.28, 0.05)}
    active  = {'ready': 'green', 'working': 'orange', 'waiting': 'red'}.get(state)

    for lx, ly, color in lights:
        if state == 'idle':
            ctx.set_source_rgba(0.42, 0.42, 0.42, 0.42)
            ctx.arc(lx, ly, lr, 0, 2 * math.pi)
            ctx.fill()
            continue

        is_on = (color == active)
        r, g, b = (on_rgb if is_on else off_rgb)[color]

        if is_on:
            # Glow — kept tight so adjacent lights don't bleed into each other
            for i in range(2, 0, -1):
                ctx.set_source_rgba(r, g, b, 0.10 * i)
                ctx.arc(lx, ly, lr + i * 2, 0, 2 * math.pi)
                ctx.fill()

        ctx.set_source_rgba(r, g, b, 1.0)
        ctx.arc(lx, ly, lr, 0, 2 * math.pi)
        ctx.fill()

        if is_on:
            ctx.set_source_rgba(1.0, 1.0, 1.0, 0.35)
            ctx.arc(lx - lr * 0.30, ly - lr * 0.30, lr * 0.35, 0, 2 * math.pi)
            ctx.fill()

    name = _icon_name(state)
    surface.write_to_png(os.path.join(ICON_DIR, f'{name}.png'))
    return name


# ── process / state helpers ──────────────────────────────────────────────────

def is_claude_running() -> bool:
    try:
        result = subprocess.run(
            ['pgrep', '-a', '-x', 'claude'],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return False
        own = str(os.getpid())
        for line in result.stdout.splitlines():
            pid = line.split()[0]
            if pid != own:
                return True
        return False
    except Exception:
        return False


def read_state() -> str:
    try:
        s = open(STATE_FILE).read().strip()
        if s not in ('ready', 'working', 'waiting'):
            return 'ready'
        return s
    except FileNotFoundError:
        return 'ready'


# ── icon theme bootstrap ────────────────────────────────────────────────────

def _write_index_theme():
    """Write index.theme so GTK recognises our custom icon sizes."""
    path = os.path.join(ICON_THEME_DIR, 'hicolor', 'index.theme')
    content = (
        '[Icon Theme]\n'
        'Name=claude-traffic-light\n'
        'Directories=22x22/apps\n\n'
        '[22x22/apps]\n'
        'Size=22\n'
        'Type=Fixed\n'
    )
    with open(path, 'w') as f:
        f.write(content)


# ── tray indicator ───────────────────────────────────────────────────────────

class TrafficLight:
    def __init__(self):
        os.makedirs(ICON_DIR, exist_ok=True)
        _write_index_theme()
        self.icons = {st: draw_icon(st) for st in TOOLTIPS}
        self._state = None

        self.ind = AppIndicator3.Indicator.new(
            'claude-traffic-light',
            _icon_name('idle'),
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        # ICON_THEME_DIR is the root containing hicolor/64x64/apps/
        self.ind.set_icon_theme_path(ICON_THEME_DIR)
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.ind.set_menu(self._make_menu())

        # Defer initial icon update until the tray widget is realized to avoid
        # GTK-CRITICAL gtk_widget_get_scale_factor assertions from AppIndicator3
        GLib.idle_add(self._deferred_start)

    def _deferred_start(self) -> bool:
        self._apply('idle')
        GLib.timeout_add(POLL_MS, self._poll)
        return False  # run once

    def _make_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label='Quit Claude Traffic Light')
        item.connect('activate', lambda _: Gtk.main_quit())
        menu.append(item)
        menu.show_all()
        return menu

    def _apply(self, state: str):
        if state == self._state:
            return
        self._state = state
        self.ind.set_icon_full(self.icons[state], TOOLTIPS[state])  # icon name, not path

    def _poll(self) -> bool:
        self._apply(read_state() if is_claude_running() else 'idle')
        return True  # keep the GLib timer alive


def main():
    import fcntl
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        lock = open(LOCK_FILE, 'w')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.write(str(os.getpid()))
        lock.flush()
    except BlockingIOError:
        print("claude-traffic-light is already running.", file=sys.stderr)
        sys.exit(1)

    TrafficLight()
    Gtk.main()


if __name__ == '__main__':
    main()
