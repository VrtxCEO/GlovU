"""
GlovU — Glove AI Traffic Sentinel

Entry point. Handles three modes:
  --install   Set up the system service, proxy settings, and CA cert
  --uninstall Remove everything
  --run       Run the sentinel (called by the service manager)
  (no args)   Same as --run, used for development
"""

from __future__ import annotations

import atexit
import sys


def _usage() -> None:
    print("Usage: python main.py [--install | --uninstall | --run]")
    sys.exit(1)


def run() -> None:
    """Start the proxy and the tray UI. Blocks until the user quits."""
    from glovu import proxy, service
    from glovu.policy import ConsumerPolicy
    from glovu.providers import ProviderRegistry
    from glovu.tray import run_ui

    # Restore proxy settings when we exit cleanly
    atexit.register(service.remove_system_proxy)

    registry = ProviderRegistry()
    policy = ConsumerPolicy(registry)

    # Set the system proxy so all HTTPS traffic routes through us
    service.set_system_proxy()

    # Background thread: mitmproxy intercepts AI traffic
    proxy.start(registry, policy)

    # Optional: try updating the provider list on startup (non-blocking)
    import threading
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
        # Push a confirmation event
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

    # Main thread: tray icon + event viewer (blocks until quit)
    run_ui(on_approve=on_approve, on_deny=on_deny)


def install() -> None:
    """Install GlovU as a background service with proxy and cert setup."""
    import os
    from glovu import service

    python_exe = sys.executable
    script_path = os.path.abspath(__file__)

    print("Installing Glove AI Protection...")

    # Generate the mitmproxy CA cert
    print("  Generating CA certificate...")
    if not service.ensure_mitm_cert_exists():
        print("  Warning: CA certificate generation failed. HTTPS inspection may not work.")
    else:
        cert_path = service.get_mitm_cert_path()
        print(f"  Installing CA certificate from {cert_path}...")
        if service.install_ca_cert(cert_path):
            print("  CA certificate installed successfully.")
        else:
            print("  Warning: CA certificate installation failed. You may need to run as administrator.")

    # Register the background service
    print("  Registering background service...")
    ok = False
    if sys.platform == "win32":
        ok = service.register_windows_service(python_exe, script_path)
    elif sys.platform == "darwin":
        ok = service.register_macos_agent(python_exe, script_path)
    else:
        ok = service.register_linux_service(python_exe, script_path)

    if ok:
        print("  Service registered. Glove will start automatically on login.")
    else:
        print("  Warning: Service registration failed. You can start Glove manually with: python main.py --run")

    # Configure system proxy
    print("  Configuring system proxy...")
    service.set_system_proxy()
    print("  System proxy configured.")

    print("\nGlove AI Protection is installed and running.")
    print("You will see a small icon in your system tray.")
    print("Glove will notify you if it protects you from something.")


def uninstall() -> None:
    """Remove GlovU completely."""
    from glovu import service

    print("Uninstalling Glove AI Protection...")
    service.remove_system_proxy()
    print("  System proxy removed.")

    if sys.platform == "win32":
        service.unregister_windows_service()
    elif sys.platform == "darwin":
        service.unregister_macos_agent()
    else:
        service.unregister_linux_service()
    print("  Service unregistered.")

    print("Glove AI Protection has been removed.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "--run" in args:
        run()
    elif "--install" in args:
        install()
    elif "--uninstall" in args:
        uninstall()
    else:
        _usage()
