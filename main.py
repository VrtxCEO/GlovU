"""
GlovU — Glove AI Traffic Sentinel

Single-executable consumer app. Double-click to install and run.

First run:  detects it's not installed, requests UAC elevation if needed,
            installs cert + proxy + autostart, then starts the tray.
Subsequent: autostart calls this exe directly — jumps straight to tray.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


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


# ---------------------------------------------------------------------------
# Core flows
# ---------------------------------------------------------------------------

def first_run() -> None:
    """
    Called the first time a user double-clicks GlovU.exe.
    Elevates to admin if needed, installs everything, then starts the tray.
    """
    # Need admin for cert install + service registration
    if sys.platform == "win32" and not _is_admin():
        _relaunch_as_admin(["--first-run"])
        return   # unreachable — relaunch exits

    _self_install_exe()
    _do_install(silent=True)
    run()


def _do_install(silent: bool = False) -> None:
    """Install cert, set proxy, register autostart."""
    from glovu import service

    def _log(msg: str) -> None:
        if not silent:
            print(msg)

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

    registry = ProviderRegistry()
    policy = ConsumerPolicy(registry)

    # Start proxy first, wait until it's actually listening before setting system proxy.
    # This ensures a crash on startup never leaves the system proxy pointing at a dead port.
    proxy.start(registry, policy)
    if _wait_for_proxy():
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
    args = sys.argv[1:]

    if "--uninstall" in args:
        uninstall()
    elif "--run" in args:
        # Called by autostart — jump straight to tray
        run()
    elif "--first-run" in args or not _is_installed():
        # First double-click: install then run
        first_run()
    else:
        # Already installed, already running from install dir — just run
        run()
