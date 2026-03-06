"""
OS service registration and system proxy configuration.

Handles:
- Installing/removing the GlovU background service
- Setting/clearing system proxy to route traffic through localhost:7777
- Installing the mitmproxy CA certificate into the OS trust store
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .proxy import PROXY_HOST, PROXY_PORT

PROXY_ADDR = f"{PROXY_HOST}:{PROXY_PORT}"


# ---------------------------------------------------------------------------
# System proxy settings
# ---------------------------------------------------------------------------

def set_system_proxy() -> None:
    """Configure the OS to route all HTTPS traffic through Glove's local proxy."""
    if sys.platform == "win32":
        _set_proxy_windows()
    elif sys.platform == "darwin":
        _set_proxy_macos()
    else:
        _set_proxy_linux()


def remove_system_proxy() -> None:
    """Remove Glove's proxy settings from the OS."""
    if sys.platform == "win32":
        _remove_proxy_windows()
    elif sys.platform == "darwin":
        _remove_proxy_macos()
    else:
        _remove_proxy_linux()


def _set_proxy_windows() -> None:
    import winreg  # type: ignore[import]
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, PROXY_ADDR)
    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
    # Bypass proxy for local addresses
    winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>")
    winreg.CloseKey(key)
    _refresh_wininet()


def _remove_proxy_windows() -> None:
    import winreg  # type: ignore[import]
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
    winreg.CloseKey(key)
    _refresh_wininet()


def _refresh_wininet() -> None:
    try:
        import ctypes
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW  # type: ignore[attr-defined]
        internet_set_option(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        internet_set_option(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception:
        pass


def _set_proxy_macos() -> None:
    # Apply to all active network interfaces
    interfaces = _macos_active_interfaces()
    for iface in interfaces:
        subprocess.run(["networksetup", "-setwebproxy", iface, PROXY_HOST, str(PROXY_PORT)], check=False)
        subprocess.run(["networksetup", "-setsecurewebproxy", iface, PROXY_HOST, str(PROXY_PORT)], check=False)
        subprocess.run(["networksetup", "-setwebproxystate", iface, "on"], check=False)
        subprocess.run(["networksetup", "-setsecurewebproxystate", iface, "on"], check=False)


def _remove_proxy_macos() -> None:
    interfaces = _macos_active_interfaces()
    for iface in interfaces:
        subprocess.run(["networksetup", "-setwebproxystate", iface, "off"], check=False)
        subprocess.run(["networksetup", "-setsecurewebproxystate", iface, "off"], check=False)


def _macos_active_interfaces() -> list[str]:
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, check=True,
        )
        lines = result.stdout.strip().splitlines()
        # Skip the header line ("An asterisk..." note)
        return [l for l in lines[1:] if l and not l.startswith("*")]
    except Exception:
        return ["Wi-Fi", "Ethernet"]


def _set_proxy_linux() -> None:
    # Write to /etc/environment (system-wide) — requires root
    _write_linux_env_proxy(PROXY_ADDR)


def _remove_proxy_linux() -> None:
    _write_linux_env_proxy(None)


def _write_linux_env_proxy(addr: str | None) -> None:
    env_file = Path("/etc/environment")
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
        # Remove existing proxy lines
        lines = [l for l in lines if not l.startswith(("http_proxy=", "https_proxy=", "HTTP_PROXY=", "HTTPS_PROXY="))]
        if addr:
            lines.extend([
                f"http_proxy=http://{addr}",
                f"https_proxy=http://{addr}",
                f"HTTP_PROXY=http://{addr}",
                f"HTTPS_PROXY=http://{addr}",
            ])
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except PermissionError:
        # Fall back to current-user environment file
        user_env = Path.home() / ".profile"
        _append_shell_proxy(user_env, addr)


def _append_shell_proxy(profile: Path, addr: str | None) -> None:
    marker_start = "# --- GlovU proxy ---"
    marker_end = "# --- end GlovU proxy ---"
    content = profile.read_text(encoding="utf-8") if profile.exists() else ""
    # Remove existing block
    if marker_start in content:
        start = content.index(marker_start)
        end = content.index(marker_end) + len(marker_end)
        content = content[:start] + content[end:]
    if addr:
        block = (
            f"\n{marker_start}\n"
            f"export http_proxy=http://{addr}\n"
            f"export https_proxy=http://{addr}\n"
            f"{marker_end}\n"
        )
        content += block
    profile.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# CA certificate installation
# ---------------------------------------------------------------------------

def install_ca_cert(cert_path: Path) -> bool:
    """Install mitmproxy's generated CA cert into the OS trust store."""
    if sys.platform == "win32":
        return _install_cert_windows(cert_path)
    elif sys.platform == "darwin":
        return _install_cert_macos(cert_path)
    else:
        return _install_cert_linux(cert_path)


def _install_cert_windows(cert_path: Path) -> bool:
    result = subprocess.run(
        ["certutil", "-addstore", "-f", "Root", str(cert_path)],
        capture_output=True,
    )
    return result.returncode == 0


def _install_cert_macos(cert_path: Path) -> bool:
    result = subprocess.run([
        "security", "add-trusted-cert",
        "-d", "-r", "trustRoot",
        "-k", "/Library/Keychains/System.keychain",
        str(cert_path),
    ], capture_output=True)
    return result.returncode == 0


def _install_cert_linux(cert_path: Path) -> bool:
    import shutil
    dest = Path("/usr/local/share/ca-certificates/glovu-ca.crt")
    try:
        shutil.copy(cert_path, dest)
        result = subprocess.run(["update-ca-certificates"], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def get_mitm_cert_path() -> Path:
    """Return the path to the mitmproxy-generated CA certificate."""
    from .events import DATA_DIR
    return DATA_DIR / "mitmproxy" / "mitmproxy-ca-cert.pem"


def ensure_mitm_cert_exists() -> bool:
    """
    Run mitmproxy briefly to generate its CA cert if it doesn't exist yet.
    Returns True if the cert file is available.
    """
    cert = get_mitm_cert_path()
    if cert.exists():
        return True

    # Boot mitmproxy for a moment to trigger cert generation
    from .events import DATA_DIR
    config_dir = DATA_DIR / "mitmproxy"
    config_dir.mkdir(parents=True, exist_ok=True)
    try:
        import asyncio
        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster

        async def _boot():
            opts = Options(
                listen_host=PROXY_HOST,
                listen_port=PROXY_PORT + 1,   # temp port
                confdir=str(config_dir),
            )
            m = DumpMaster(opts, with_termlog=False, with_dumper=False)
            await asyncio.sleep(0.5)
            m.shutdown()

        asyncio.run(_boot())
    except Exception:
        pass

    return cert.exists()


# ---------------------------------------------------------------------------
# Windows service registration (using sc.exe + a helper launcher script)
# ---------------------------------------------------------------------------

def register_windows_service(python_exe: str, script_path: str) -> bool:
    """Register GlovU as a Windows service that starts at login."""
    nssm = _find_nssm()
    if nssm:
        result = subprocess.run([
            nssm, "install", "GlovU", python_exe, script_path, "--run",
        ], capture_output=True)
        if result.returncode == 0:
            subprocess.run([nssm, "set", "GlovU", "DisplayName", "Glove AI Protection"], check=False)
            subprocess.run([nssm, "set", "GlovU", "Description",
                           "Monitors and protects AI traffic on your device."], check=False)
            subprocess.run([nssm, "set", "GlovU", "Start", "SERVICE_AUTO_START"], check=False)
            subprocess.run(["sc", "start", "GlovU"], check=False)
            return True
    # Fallback: use Task Scheduler for user-level autostart
    return _register_task_scheduler(python_exe, script_path)


def _find_nssm() -> str | None:
    import shutil
    return shutil.which("nssm")


def _register_task_scheduler(python_exe: str, script_path: str) -> bool:
    result = subprocess.run([
        "schtasks", "/create", "/tn", "GlovU",
        "/tr", f'"{python_exe}" "{script_path}" --run',
        "/sc", "onlogon", "/rl", "highest", "/f",
    ], capture_output=True)
    return result.returncode == 0


def unregister_windows_service() -> bool:
    nssm = _find_nssm()
    if nssm:
        subprocess.run([nssm, "stop", "GlovU"], check=False)
        subprocess.run([nssm, "remove", "GlovU", "confirm"], check=False)
    subprocess.run(["schtasks", "/delete", "/tn", "GlovU", "/f"], check=False)
    return True


# ---------------------------------------------------------------------------
# macOS LaunchAgent
# ---------------------------------------------------------------------------

def register_macos_agent(python_exe: str, script_path: str) -> bool:
    plist = _macos_plist_content(python_exe, script_path)
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.glovu.sentinel.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist, encoding="utf-8")
    result = subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True)
    return result.returncode == 0


def unregister_macos_agent() -> bool:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.glovu.sentinel.plist"
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    plist_path.unlink(missing_ok=True)
    return True


def _macos_plist_content(python_exe: str, script_path: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.glovu.sentinel</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>{script_path}</string>
        <string>--run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/glovu.err</string>
    <key>StandardOutPath</key>
    <string>/tmp/glovu.out</string>
</dict>
</plist>
"""


# ---------------------------------------------------------------------------
# Linux systemd user service
# ---------------------------------------------------------------------------

def register_linux_service(python_exe: str, script_path: str) -> bool:
    unit = _linux_unit_content(python_exe, script_path)
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "glovu.service"
    unit_path.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    result = subprocess.run(["systemctl", "--user", "enable", "--now", "glovu"], capture_output=True)
    return result.returncode == 0


def unregister_linux_service() -> bool:
    subprocess.run(["systemctl", "--user", "disable", "--now", "glovu"], check=False)
    unit_path = Path.home() / ".config" / "systemd" / "user" / "glovu.service"
    unit_path.unlink(missing_ok=True)
    return True


def _linux_unit_content(python_exe: str, script_path: str) -> str:
    return f"""[Unit]
Description=Glove AI Protection Sentinel
After=network.target

[Service]
ExecStart={python_exe} {script_path} --run
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
