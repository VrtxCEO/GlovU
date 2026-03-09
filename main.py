"""
GlovU — Glove AI Traffic Sentinel

Single-executable consumer app. Double-click to install and run.

First run:  detects it's not installed, requests UAC elevation if needed,
            installs cert + proxy + autostart, then starts the tray.
Subsequent: autostart calls this exe directly — jumps straight to tray.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from glovu.app_logging import configure_logging, get_logger

_single_instance_handle: object | None = None


def _acquire_single_instance() -> bool:
    """Prevent multiple GlovU processes from running at the same time."""
    global _single_instance_handle

    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\GlovU.Singleton")
        if not handle:
            return True

        error_already_exists = 183
        if kernel32.GetLastError() == error_already_exists:
            kernel32.CloseHandle(handle)
            return False

        _single_instance_handle = handle
        return True

    from glovu.events import DATA_DIR

    lock_path = DATA_DIR / "glovu.lock"
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return False

    _single_instance_handle = lock_file
    return True


def _release_single_instance() -> None:
    global _single_instance_handle
    if _single_instance_handle is None:
        return

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.CloseHandle(_single_instance_handle)
    else:
        try:
            _single_instance_handle.close()
        except Exception:
            pass

    _single_instance_handle = None


def _show_already_running_notice() -> None:
    message = "GlovU is already running. Use the tray icon or quit it before launching another copy."
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "GlovU", 0x40)
            return
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("GlovU", message)
        root.destroy()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Installed location — where the exe copies itself on first run
# ---------------------------------------------------------------------------

def _install_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "GlovU"


def _installed_exe() -> Path:
    return _install_dir() / "GlovU.exe"


def _is_installed() -> bool:
    """Check whether Glove has been set up on this machine."""
    from glovu.events import DATA_DIR
    return (DATA_DIR / "state.json").exists() or _installed_exe().exists()


def _is_running_from_install_dir() -> bool:
    exe = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    try:
        exe.relative_to(_install_dir())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# UAC elevation (Windows)
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    if sys.platform != "win32":
        return os.geteuid() == 0  # type: ignore[attr-defined]
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin(extra_args: list[str] | None = None) -> None:
    """Re-launch this process with UAC elevation and exit the current one."""
    import ctypes
    exe = sys.executable
    args = " ".join([f'"{a}"' for a in (sys.argv + (extra_args or []))])
    _release_single_instance()
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Self-copy to install directory (so autostart runs from a stable path)
# ---------------------------------------------------------------------------

def _self_install_exe() -> None:
    """Copy this executable to the install directory."""
    if not getattr(sys, "frozen", False):
        return   # running as a .py script during dev — skip copy
    src = Path(sys.executable)
    dest = _installed_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src != dest:
        import shutil
        shutil.copy2(src, dest)


def _launch_installed_exe(extra_args: list[str] | None = None) -> None:
    """Launch the installed executable, then exit the current process."""
    target = _installed_exe()
    cmd = [str(target), *(extra_args or [])]
    get_logger().info("Launching installed executable. target=%s args=%s", target, extra_args or [])
    _release_single_instance()
    subprocess.Popen(cmd, close_fds=True)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Minimal install prompt (first run)
# ---------------------------------------------------------------------------

def _prompt_install() -> bool:
    """
    Show a simple "Install" prompt on first run.
    Returns True if the user chooses Install, False otherwise.
    """
    try:
        import tkinter as tk
    except Exception:
        # If tkinter is unavailable, assume install.
        return True

    result = {"ok": False}

    root = tk.Tk()
    root.title("GlovU Installer")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    bg = "#FFFFFF"
    accent = "#1E293B"
    muted = "#475569"
    root.configure(bg=bg)

    def _close() -> None:
        root.destroy()

    def _install() -> None:
        result["ok"] = True
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _close)

    pad = 20
    frame = tk.Frame(root, bg=bg, padx=pad, pady=pad)
    frame.pack(fill="both", expand=True)

    # Optional brand icon
    icon_photo = None
    try:
        from PIL import Image, ImageTk  # type: ignore
        from glovu.assets import asset_path
        icon_path = asset_path("glovu-icon.png")
        if icon_path.exists():
            img = Image.open(icon_path).convert("RGBA")
            img.thumbnail((96, 96))
            icon_photo = ImageTk.PhotoImage(img)
            # Window icon (smaller)
            small = img.copy()
            small.thumbnail((32, 32))
            icon_small = ImageTk.PhotoImage(small)
            root.iconphoto(True, icon_small)
            root._icon_ref = icon_small  # keep reference alive
    except Exception:
        icon_path = None

    top = tk.Frame(frame, bg=bg)
    top.pack(fill="x")

    if icon_photo:
        lbl_icon = tk.Label(top, image=icon_photo, bg=bg)
        lbl_icon.image = icon_photo
        lbl_icon.pack(side="left", padx=(0, 14))

    text_col = tk.Frame(top, bg=bg)
    text_col.pack(side="left", fill="x", expand=True)

    tk.Label(
        text_col,
        text="GlovU Protection",
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 16, "bold"),
        fg=accent,
        bg=bg,
    ).pack(anchor="w")

    tk.Label(
        text_col,
        text="Install and start protection for AI traffic on this device.",
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
        fg=muted,
        bg=bg,
        justify="left",
    ).pack(anchor="w", pady=(4, 0))

    body = (
        "- Installs the system tray app and local protection layer\n"
        "- Runs in the background until you quit it\n"
        "- Re-open anytime by double-clicking GlovU"
    )
    tk.Label(
        frame,
        text=body,
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
        fg=accent,
        bg=bg,
        justify="left",
    ).pack(anchor="w", pady=(12, 6))

    tk.Label(
        frame,
        text="You may see a Windows permission prompt during install.",
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
        fg=muted,
        bg=bg,
        justify="left",
    ).pack(anchor="w", pady=(0, 12))

    btn_row = tk.Frame(frame, bg=bg)
    btn_row.pack(anchor="e")

    tk.Button(
        btn_row,
        text="Cancel",
        command=_close,
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
        relief="flat",
        padx=12,
        pady=6,
        bg="#F1F5F9",
        fg=accent,
        activebackground="#E2E8F0",
        cursor="hand2",
    ).pack(side="left", padx=(0, 8))

    tk.Button(
        btn_row,
        text="Install",
        command=_install,
        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10, "bold"),
        relief="flat",
        padx=14,
        pady=6,
        bg="#22C55E",
        fg="white",
        activebackground="#16A34A",
        cursor="hand2",
    ).pack(side="left")

    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.lift()
    root.focus_force()
    root.mainloop()

    return result["ok"]


# ---------------------------------------------------------------------------
# Core flows
# ---------------------------------------------------------------------------

def first_run() -> None:
    """
    Called the first time a user double-clicks GlovU.exe.
    Elevates to admin if needed, installs everything, then starts the tray.
    """
    logger = get_logger()
    logger.info("Starting first-run flow.")
    # Need admin for cert install + service registration
    if sys.platform == "win32" and not _is_admin():
        logger.info("Requesting elevation for first-run install.")
        _relaunch_as_admin(["--first-run"])
        return   # unreachable — relaunch exits

    _self_install_exe()
    _do_install(silent=True)
    logger.info("First-run install completed. Launching installed runtime.")
    _launch_installed_exe(["--run"])


def _do_install(silent: bool = False) -> None:
    """Install cert, set proxy, register autostart."""
    from glovu import service
    logger = get_logger()

    def _log(msg: str) -> None:
        if not silent:
            print(msg)
        logger.info(msg)

    # Stable exe path — autostart points here
    exe_path = str(_installed_exe()) if getattr(sys, "frozen", False) else sys.executable
    script_arg = "" if getattr(sys, "frozen", False) else f'"{os.path.abspath(__file__)}"'

    _log("Generating CA certificate...")
    if service.ensure_mitm_cert_exists():
        cert_path = service.get_mitm_cert_path()
        service.install_ca_cert(cert_path)

    _log("Registering autostart...")
    if sys.platform == "win32":
        _register_autostart_windows(exe_path)
    elif sys.platform == "darwin":
        service.register_macos_agent(exe_path, script_arg)
    else:
        service.register_linux_service(exe_path, script_arg)

    # Mark as installed
    from glovu.events import DATA_DIR
    (DATA_DIR / "state.json").parent.mkdir(parents=True, exist_ok=True)
    if not (DATA_DIR / "state.json").exists():
        (DATA_DIR / "state.json").write_text("{}", encoding="utf-8")


def _register_autostart_windows(exe_path: str) -> None:
    """Add GlovU to the current user's autostart via the registry (no admin needed)."""
    import winreg  # type: ignore[import]
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, "GlovU", 0, winreg.REG_SZ, f'"{exe_path}"')
    winreg.CloseKey(key)


def _wait_for_proxy(timeout: float = 10.0) -> bool:
    """Poll localhost:7777 until mitmproxy is accepting connections or timeout."""
    import socket
    import time
    from glovu.proxy import PROXY_HOST, PROXY_PORT
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def run() -> None:
    """Start the proxy and the tray UI. Blocks until the user quits."""
    import atexit
    import threading
    from glovu import proxy, service
    from glovu.policy import ConsumerPolicy
    from glovu.providers import ProviderRegistry
    from glovu.tray import run_ui

    atexit.register(service.remove_system_proxy)
    get_logger().info("Runtime starting.")

    registry = ProviderRegistry()
    policy = ConsumerPolicy(registry)

    # Disable QUIC immediately so browsers use TCP before the proxy is even set.
    if sys.platform == "win32":
        service._disable_browser_quic()

    # Start proxy first, wait until it's actually listening before setting system proxy.
    # This ensures a crash on startup never leaves the system proxy pointing at a dead port.
    proxy.start(registry, policy)
    if _wait_for_proxy():
        get_logger().info("Proxy is listening. Applying system proxy.")
        service.set_system_proxy()
    else:
        # Proxy failed to start — run in tray-only mode, don't touch system proxy
        from glovu.events import event_queue, new_event
        event_queue.put(new_event(
            "suspicious_activity", "GlovU", "proxy", "GlovU",
            what="Glove could not start its protection layer.",
            why="The proxy failed to bind to port 7777. Another app may be using it.",
            action="Protection is inactive. Your internet connection is unaffected.",
        ))

    threading.Thread(
        target=registry.try_update_from_remote,
        daemon=True,
        name="glovu-update",
    ).start()
    get_logger().info("Tray UI starting.")

    def on_approve(event) -> None:
        from glovu.events import event_queue, new_event
        if event.kind == "blocked_unknown_app":
            policy.approve_app(event.app_name)
        elif event.kind in ("blocked_unknown_endpoint", "new_local_model"):
            policy.approve_endpoint(event.provider_host, event.provider_name)
        elif event.kind == "blocked_unknown_model":
            policy.approve_model(event.provider_host, event.model)
        event_queue.put(new_event(
            "approved", event.app_name, event.provider_host, event.provider_name,
            what=f"Approved: {event.provider_name or event.app_name}.",
            why="You chose to allow this.",
            action="Future requests will be allowed automatically.",
        ))

    def on_deny(event) -> None:
        from glovu.events import event_queue, new_event
        if event.kind == "blocked_unknown_app":
            policy.deny_app(event.app_name)
        elif event.kind in ("blocked_unknown_endpoint", "new_local_model"):
            policy.deny_endpoint(event.provider_host, event.provider_name)
        event_queue.put(new_event(
            "denied", event.app_name, event.provider_host, event.provider_name,
            what=f"Denied: {event.provider_name or event.app_name}.",
            why="You chose to block this.",
            action="All future requests from this source will be blocked.",
        ))

    run_ui(on_approve=on_approve, on_deny=on_deny)


def uninstall() -> None:
    """Remove GlovU completely."""
    from glovu import service
    get_logger().info("Uninstall requested.")
    service.remove_system_proxy()
    if sys.platform == "win32":
        _remove_autostart_windows()
        service.unregister_windows_service()
    elif sys.platform == "darwin":
        service.unregister_macos_agent()
    else:
        service.unregister_linux_service()


def _remove_autostart_windows() -> None:
    try:
        import winreg  # type: ignore[import]
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, "GlovU")
        winreg.CloseKey(key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    configure_logging()
    args = sys.argv[1:]
    get_logger().info("Application launch. frozen=%s args=%s", getattr(sys, "frozen", False), args)

    if not _acquire_single_instance():
        get_logger().warning("Blocked duplicate launch. args=%s", args)
        if not args:
            _show_already_running_notice()
        sys.exit(0)

    if "--uninstall" in args:
        uninstall()
    elif "--run" in args:
        # Called by autostart — jump straight to tray
        run()
    elif "--first-run" in args or "--install" in args:
        # Relaunched after UAC elevation — install then run
        first_run()
    elif getattr(sys, "frozen", False) and not _is_running_from_install_dir():
        get_logger().info("External launcher detected. installed=%s", _is_installed())
        if not _is_installed():
            if _prompt_install():
                first_run()
        else:
            _self_install_exe()
            _do_install(silent=True)
            _launch_installed_exe(["--run"])
    elif not _is_installed():
        # First double-click: show install prompt, then install + run
        if _prompt_install():
            first_run()
    else:
        # Already installed, already running from install dir — just run
        run()
