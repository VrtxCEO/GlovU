# macOS Validation Checklist

## Current Position

macOS should be treated as experimental.

Reasons:

- Installer is a shell script, not a packaged `.app` or `.pkg`
- Target machine must already have Python 3.11+
- Real-device validation has not been completed
- No signing / notarization flow exists

## Current Install Path

- Installer: `installer/macos/install.sh`
- Install location: `~/Library/Application Support/GlovU/app`
- Startup mechanism: LaunchAgent via `com.glovu.sentinel.plist`

## Manual Validation Checklist

| ID | Scenario | Expected Result |
| --- | --- | --- |
| M-01 | Fresh install on a clean Mac with Python 3.11+ | Installer completes and app launches |
| M-02 | Cert install | CA certificate installs successfully without leaving trust-store confusion |
| M-03 | Proxy enable | System proxy is applied and AI traffic is intercepted |
| M-04 | Menu bar presence | App appears in the menu bar / tray equivalent |
| M-05 | Quit cleanup | Quitting the app removes proxy settings cleanly |
| M-06 | Relaunch | Relaunching the app works after quit |
| M-07 | Login autostart | App starts after logout/login via LaunchAgent |
| M-08 | Update existing install | Running a newer installer over an older install refreshes the app cleanly |
| M-09 | Uninstall | App files, LaunchAgent, proxy settings, and cert cleanup all behave correctly |
| M-10 | Browser validation | Safari / Chrome / Edge traffic behaves correctly with supported AI sites |

## Known Product Gaps Before Selling macOS

- No packaged macOS app experience
- No code signing or notarization
- No validated support flow for macOS-specific proxy/certificate issues
- No proof yet that tray behavior and quit cleanup are stable on real devices

## Minimum Exit Criteria For Selling macOS

- `M-01` through `M-09` pass on at least 2 real Macs
- One Apple Silicon Mac and one Intel Mac, if Intel support is intended
- Signed and notarized distribution path exists
- Support docs exist for cert, proxy, and LaunchAgent troubleshooting

## Recommendation

- Do not market macOS as generally available yet
- Keep macOS as waitlist / preview until the checklist above is completed
