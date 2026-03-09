"""
System tray icon and event viewer window.

Three tray states:
  protected  — green dot, everything is fine
  issue      — amber dot, something needs attention
  paused     — grey dot, protection is off

The event viewer window only appears when something happens.
It shows: what happened / why / what Glove did + optional approve/deny buttons.
"""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from queue import Empty, Queue
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from .app_logging import get_logger
from .events import GlovuEvent, event_queue
from .assets import asset_path

# Thread-safe queue for scheduling work on the tkinter main thread
_ui_queue: Queue[Callable] = Queue()

# Tray icon singleton
_icon: Optional[pystray.Icon] = None

# Current protection state
_protected = True

# Recent event history (last 10)
_event_history: deque[GlovuEvent] = deque(maxlen=10)

# Popup dedup: track last time each (kind, app) pair showed a popup
import time as _time
_popup_last_shown: dict[tuple[str, str], float] = {}
_POPUP_COOLDOWN = 30.0   # seconds — don't re-pop the same event type from same app


# ---------------------------------------------------------------------------
# Icon images
# ---------------------------------------------------------------------------

_BRAND_BASE: Image.Image | None | bool = None


def _load_brand_icon(size: int) -> Image.Image | None:
    """Load branded icon from assets, scaled to the requested size."""
    global _BRAND_BASE
    if _BRAND_BASE is None:
        try:
            path = asset_path("glovu-icon.png")
            if path.exists():
                _BRAND_BASE = Image.open(path).convert("RGBA")
            else:
                _BRAND_BASE = False
        except Exception:
            _BRAND_BASE = False
    if _BRAND_BASE is False:
        return None
    if isinstance(_BRAND_BASE, Image.Image):
        img = _BRAND_BASE.copy()
        img.thumbnail((size, size))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        x = (size - img.width) // 2
        y = (size - img.height) // 2
        canvas.paste(img, (x, y), img)
        return canvas
    return None


def _make_icon(state: str) -> Image.Image:
    """Generate a tray icon with branded base and status indicator."""
    size = 64
    img = _load_brand_icon(size)
    if img is None:
        # Fallback to a simple colored circle icon for the tray.
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        margin = 4
        colors = {
            "protected": "#22C55E",   # green
            "issue":     "#F59E0B",   # amber
            "paused":    "#94A3B8",   # grey
        }
        color = colors.get(state, "#22C55E")
        draw.ellipse([margin, margin, size - margin, size - margin], fill=color)

        # Small inner dot for "heartbeat" feel
        inner = size // 2
        r = size // 8
        draw.ellipse([inner - r, inner - r, inner + r, inner + r], fill="white")
        return img

    draw = ImageDraw.Draw(img)
    colors = {
        "protected": "#22C55E",   # green
        "issue":     "#F59E0B",   # amber
        "paused":    "#94A3B8",   # grey
    }
    color = colors.get(state, "#22C55E")
    dot_r = size // 6
    dot_margin = 3
    x0 = size - dot_r * 2 - dot_margin
    y0 = size - dot_r * 2 - dot_margin
    x1 = x0 + dot_r * 2
    y1 = y0 + dot_r * 2
    draw.ellipse([x0, y0, x1, y1], fill=color, outline="white")
    return img


_ICONS = {state: _make_icon(state) for state in ("protected", "issue", "paused")}


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------

def _on_toggle(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    global _protected
    _protected = not _protected
    label = "Protected" if _protected else "Paused"
    icon.icon = _ICONS["protected" if _protected else "paused"]
    icon.notify(f"Glove is now {label}.", "Glove AI Protection")


def _on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    from . import proxy, service
    get_logger().info("Tray quit requested.")
    # Remove proxy immediately — atexit is unreliable in frozen exes.
    # This ensures the system proxy is always cleared before the process dies.
    service.remove_system_proxy()
    proxy.stop()
    icon.stop()
    # Signal tkinter main loop to exit
    _ui_queue.put(lambda: _root.quit())


def _on_open_log(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    _ui_queue.put(_show_activity_log)


def _build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Glove AI Protection", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Activity Log", _on_open_log),
        pystray.MenuItem(
            lambda item: "Pause Protection" if _protected else "Resume Protection",
            _on_toggle,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )


def start_tray() -> None:
    """Start the tray icon in a daemon thread (required on Windows/Linux)."""
    import threading
    global _icon
    _icon = pystray.Icon(
        name="GlovU",
        icon=_ICONS["protected"],
        title="Glove AI Protection",
        menu=_build_menu(),
    )
    t = threading.Thread(target=_icon.run, daemon=True, name="glovu-tray")
    t.start()


def set_state(state: str) -> None:
    """Update tray icon state from any thread."""
    global _icon
    if _icon:
        _ui_queue.put(lambda: _icon.__setattr__("icon", _ICONS.get(state, _ICONS["protected"])))


def notify(title: str, message: str) -> None:
    """Show a system notification from any thread."""
    global _icon
    if _icon:
        _ui_queue.put(lambda: _icon.notify(message, title))


# ---------------------------------------------------------------------------
# Activity log window
# ---------------------------------------------------------------------------

def _show_activity_log() -> None:
    """Show a window listing the last 10 events. Must be called from main thread."""
    if _root is None:
        return

    win = tk.Toplevel(_root)
    win.title("Glove — Activity Log")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    bg = "#FFFFFF"
    accent = "#1E293B"
    muted = "#64748B"
    row_hover = "#F8FAFC"
    win.configure(bg=bg)
    font_ui = ("Segoe UI" if sys.platform == "win32" else "Helvetica", 10)
    font_bold = ("Segoe UI" if sys.platform == "win32" else "Helvetica", 13, "bold")
    font_small = ("Segoe UI" if sys.platform == "win32" else "Helvetica", 8, "bold")

    # Header
    header = tk.Frame(win, bg=bg, padx=20, pady=16)
    header.pack(fill="x")
    tk.Label(header, text="Activity Log", font=font_bold, fg=accent, bg=bg).pack(side="left")
    tk.Label(header, text="last 10 events", font=font_small, fg=muted, bg=bg).pack(side="left", padx=(8, 0), pady=3)

    tk.Frame(win, height=1, bg="#E2E8F0").pack(fill="x", padx=20)

    kind_colors = {
        "blocked_unknown_endpoint": "#EF4444",
        "blocked_unknown_app":      "#F59E0B",
        "blocked_unknown_model":    "#F59E0B",
        "redacted_sensitive_data":  "#F59E0B",
        "suspicious_activity":      "#F59E0B",
        "new_local_model":          "#EF4444",
        "approved":                 "#22C55E",
        "denied":                   "#EF4444",
    }
    kind_labels = {
        "blocked_unknown_endpoint": "BLOCKED",
        "blocked_unknown_app":      "APP CHECK",
        "blocked_unknown_model":    "MODEL CHECK",
        "redacted_sensitive_data":  "REDACTED",
        "suspicious_activity":      "ALERT",
        "new_local_model":          "LOCAL AI",
        "approved":                 "APPROVED",
        "denied":                   "DENIED",
    }

    history = list(_event_history)

    if not history:
        tk.Label(
            win, text="No events yet.",
            font=font_ui, fg=muted, bg=bg, padx=20, pady=20,
        ).pack()
    else:
        scroll_frame = tk.Frame(win, bg=bg)
        scroll_frame.pack(fill="both", expand=True)

        for i, evt in enumerate(reversed(history)):
            color = kind_colors.get(evt.kind, "#F59E0B")
            badge = kind_labels.get(evt.kind, evt.kind.upper())

            row = tk.Frame(scroll_frame, bg=bg, padx=20, pady=10, cursor="hand2")
            row.pack(fill="x")

            # Color dot
            dot = tk.Canvas(row, width=10, height=10, bg=bg, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=color, outline="")
            dot.pack(side="left", padx=(0, 8), pady=2)

            # Badge
            badge_lbl = tk.Label(
                row, text=badge,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 7, "bold"),
                fg=color, bg=bg, width=10, anchor="w",
            )
            badge_lbl.pack(side="left")

            # Summary text
            summary = evt.what[:60] + ("…" if len(evt.what) > 60 else "")
            summary_lbl = tk.Label(
                row, text=summary,
                font=font_ui, fg=accent, bg=bg, anchor="w", justify="left",
            )
            summary_lbl.pack(side="left", fill="x", expand=True)

            # Timestamp — stored as ISO string e.g. "2026-03-06T14:23:01.123+00:00"
            try:
                ts = evt.timestamp[11:19]   # "HH:MM:SS" slice
            except Exception:
                ts = ""
            tk.Label(row, text=ts, font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 8),
                     fg=muted, bg=bg).pack(side="right")

            # Hover + click to open detail
            def _bind_row(r, e, *widgets):
                def _enter(_):
                    for w in [r] + list(widgets):
                        try: w.configure(bg=row_hover)
                        except Exception: pass
                def _leave(_):
                    for w in [r] + list(widgets):
                        try: w.configure(bg=bg)
                        except Exception: pass
                def _click(_):
                    show_event_window(e)
                for w in [r] + list(widgets):
                    w.bind("<Enter>", _enter)
                    w.bind("<Leave>", _leave)
                    w.bind("<Button-1>", _click)
            _bind_row(row, evt, dot, badge_lbl, summary_lbl)

            if i < len(history) - 1:
                tk.Frame(scroll_frame, height=1, bg="#F1F5F9").pack(fill="x", padx=20)

    tk.Frame(win, height=1, bg="#E2E8F0").pack(fill="x", padx=20)
    tk.Button(
        win, text="Close",
        font=font_ui, relief="flat", padx=14, pady=6, cursor="hand2",
        bg="#F1F5F9", fg=accent, activebackground="#E2E8F0",
        command=win.destroy,
    ).pack(anchor="e", padx=20, pady=12)

    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.lift()


# ---------------------------------------------------------------------------
# Event viewer window
# ---------------------------------------------------------------------------

_root: Optional[tk.Tk] = None


def _build_root() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()   # hidden — only shown when events appear
    root.title("Glove AI Protection")
    root.resizable(False, False)
    return root


def show_event_window(
    event: GlovuEvent,
    on_approve: Optional[Callable] = None,
    on_deny: Optional[Callable] = None,
) -> None:
    """Display the minimal event viewer. Must be called from the main thread."""
    if _root is None:
        return

    win = tk.Toplevel(_root)
    win.title("Glove AI Protection")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    # Colors
    bg = "#FFFFFF"
    accent = "#1E293B"
    muted = "#64748B"
    green = "#22C55E"
    red = "#EF4444"
    amber = "#F59E0B"
    win.configure(bg=bg)

    # Determine indicator color by event kind
    kind_colors = {
        "blocked_unknown_endpoint": red,
        "blocked_unknown_app": amber,
        "blocked_unknown_model": amber,
        "redacted_sensitive_data": amber,
        "suspicious_activity": amber,
        "new_local_model": red,
        "approved": green,
        "denied": red,
    }
    indicator_color = kind_colors.get(event.kind, amber)

    pad = 20
    wrap = 380

    # Header row: colored indicator + title
    header = tk.Frame(win, bg=bg, padx=pad, pady=pad)
    header.pack(fill="x")

    canvas = tk.Canvas(header, width=14, height=14, bg=bg, highlightthickness=0)
    canvas.create_oval(1, 1, 13, 13, fill=indicator_color, outline="")
    canvas.pack(side="left", padx=(0, 8), pady=2)

    tk.Label(
        header, text="Glove AI Protection",
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 13, "bold"),
        fg=accent, bg=bg,
    ).pack(side="left")

    # Divider
    tk.Frame(win, height=1, bg="#E2E8F0").pack(fill="x", padx=pad)

    # Content
    content = tk.Frame(win, bg=bg, padx=pad, pady=12)
    content.pack(fill="x")

    def _section(label: str, text: str) -> None:
        tk.Label(
            content, text=label.upper(),
            font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 8, "bold"),
            fg=muted, bg=bg, anchor="w",
        ).pack(fill="x", pady=(8, 1))
        tk.Label(
            content, text=text,
            font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
            fg=accent, bg=bg, anchor="w", justify="left", wraplength=wrap,
        ).pack(fill="x")

    _section("What happened", event.what)
    _section("Why", event.why)
    _section("What Glove did", event.action)

    if event.redacted_fields:
        _section("Redacted", ", ".join(event.redacted_fields))

    # Buttons
    tk.Frame(win, height=1, bg="#E2E8F0").pack(fill="x", padx=pad)
    btn_row = tk.Frame(win, bg=bg, padx=pad, pady=12)
    btn_row.pack(fill="x")

    btn_style = {
        "font": ("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
        "relief": "flat",
        "padx": 14, "pady": 6,
        "cursor": "hand2",
    }

    if event.requires_decision and on_approve and on_deny:
        tk.Button(
            btn_row, text="Approve",
            bg=green, fg="white", activebackground="#16A34A",
            command=lambda: [on_approve(event), win.destroy()],
            **btn_style,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row, text="Deny",
            bg=red, fg="white", activebackground="#DC2626",
            command=lambda: [on_deny(event), win.destroy()],
            **btn_style,
        ).pack(side="left")

    tk.Button(
        btn_row, text="Dismiss",
        bg="#F1F5F9", fg=accent, activebackground="#E2E8F0",
        command=win.destroy,
        **btn_style,
    ).pack(side="right")

    # Center on screen
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.lift()


# ---------------------------------------------------------------------------
# Main UI loop (call from main thread)
# ---------------------------------------------------------------------------

def run_ui(
    on_approve: Optional[Callable] = None,
    on_deny: Optional[Callable] = None,
) -> None:
    """
    Run the tkinter main loop. Polls the event queue and updates tray state.
    Must be called from the main thread.
    """
    global _root
    _root = _build_root()
    start_tray()

    _POLL_MS = 150

    def _poll() -> None:
        # Process any pending UI callbacks
        try:
            while True:
                cb = _ui_queue.get_nowait()
                try:
                    cb()
                except Exception:
                    pass
        except Empty:
            pass

        # Check for new events from the proxy
        try:
            while True:
                evt = event_queue.get_nowait()
                _handle_event(evt, on_approve, on_deny)
        except Empty:
            pass

        _root.after(_POLL_MS, _poll)

    def _handle_event(
        evt: GlovuEvent,
        on_approve: Optional[Callable],
        on_deny: Optional[Callable],
    ) -> None:
        # Record in history
        _event_history.append(evt)

        # Deduplicate popups — same (kind, app) pair silently logs but doesn't re-pop
        dedup_key = (evt.kind, evt.app_name)
        now = _time.monotonic()
        last = _popup_last_shown.get(dedup_key, 0.0)
        show_popup = (now - last) >= _POPUP_COOLDOWN or evt.requires_decision
        if show_popup:
            _popup_last_shown[dedup_key] = now

        # Update tray state
        if evt.kind in ("blocked_unknown_endpoint", "new_local_model", "blocked_unknown_app",
                        "blocked_unknown_model", "suspicious_activity"):
            if _icon:
                _icon.icon = _ICONS["issue"]
                if show_popup:
                    _icon.notify(
                        _short_description(evt),
                        "Glove AI Protection",
                    )

        # Show the event window (only if not suppressed by cooldown)
        if show_popup:
            show_event_window(evt, on_approve=on_approve, on_deny=on_deny)

        # After a delay, revert to protected state if no more pending events
        def _maybe_restore() -> None:
            if event_queue.empty() and _icon:
                _icon.icon = _ICONS["protected" if _protected else "paused"]
        _root.after(5000, _maybe_restore)

    _root.after(_POLL_MS, _poll)
    _root.mainloop()


def _short_description(evt: GlovuEvent) -> str:
    descriptions = {
        "blocked_unknown_endpoint": "Blocked access to an unknown AI service",
        "blocked_unknown_app":      "An app wants to use AI — tap to approve",
        "blocked_unknown_model":    "Unusual AI model detected",
        "redacted_sensitive_data":  "Sensitive data was redacted before sending",
        "suspicious_activity":      "Unusual AI activity detected",
        "new_local_model":          "Local AI server detected — tap to approve",
    }
    return descriptions.get(evt.kind, "Glove protected you from an unsafe AI action")
