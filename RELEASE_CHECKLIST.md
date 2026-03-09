# GlovU Release Checklist

## Support Matrix

| Platform | Current Status | Sellability |
| --- | --- | --- |
| Windows | Packaged `GlovU.exe`, tested install/runtime flow, basic regression tests | Paid beta / pilot |
| macOS | Script-based installer, requires Python 3.11+, not field-tested | Experimental only |
| Linux | Script-based installer, requires Python 3.11+, not field-tested | Experimental only |

## Ready Now

- Windows `GlovU.exe` builds successfully.
- First-run install dialog exists.
- Duplicate launches are blocked.
- External launcher refreshes the installed copy before running.
- Crash logging writes to `%APPDATA%\\GlovU\\glovu.log`.
- Basic launcher and redaction regression tests exist in `tests/`.

## Must Validate Before Selling Broadly

- Clean-machine Windows install on multiple PCs.
- Windows update path when an older installed copy already exists.
- Quit / relaunch / reboot / autostart behavior on Windows.
- Uninstall cleanup on Windows, including proxy and certificate cleanup.
- SmartScreen / code-signing plan for Windows builds.
- Real pricing enforcement or licensing if usage limits will be sold.

## Can Be Solved In Code

- Expand automated coverage beyond launcher and redaction behavior.
- Add diagnostics / export flow for logs and current proxy state.
- Add explicit version reporting in the app and build output.
- Improve installer and uninstall messaging for partial-failure cases.

## Requires External Assets Or Manual Validation

- Windows code-signing certificate and signing pipeline.
- Real device testing on clean Windows machines.
- Real device testing on macOS.
- Real device testing on Linux distributions you intend to support.
- License server, billing integration, or other hard pricing enforcement.
- Customer support flow for collecting logs and handling install failures.

## Not Ready To Promise Yet

- Seamless macOS consumer install.
- Seamless Linux consumer install.
- Self-serve onboarding with no manual support.
- Silent auto-update / rollback.
- Broad compatibility claims across browsers and desktop AI clients.

## macOS Gaps

- Current installer is `installer/macos/install.sh`, not a packaged `.app` or `.pkg`.
- Requires Python 3.11+ on the target machine.
- Has not been tested on a real macOS device.
- Needs install, relaunch, menu bar, proxy, cert, and uninstall validation.

## Linux Gaps

- Current installer is `installer/linux/install.sh`, not a packaged app.
- Requires Python 3.11+ and user/system package dependencies.
- Has not been tested on target distros.
- Needs distro-specific validation for proxy behavior and service startup.

## Recommended Go-To-Market Position

- Sell Windows first.
- Position macOS and Linux as preview / waitlist until tested.
- Treat the current release as founder-led beta, not polished mass-market self-serve.

## Exit Criteria For Broader Selling

- 3 to 5 clean Windows machines validated end-to-end.
- Signed Windows executable.
- One uninstall/reinstall cycle validated on each tested machine.
- License or billing gate implemented if pricing depends on limits.
- A short support playbook for common install failures and log collection.
