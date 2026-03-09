# Windows Beta Test Matrix

## Scope

- Product: `GlovU.exe`
- Target: Windows paid beta / pilot validation
- Goal: prove install, relaunch, quit, update, reboot, and uninstall behavior on real machines

## Test Environment To Capture

- Windows version
- Browser(s) installed
- AI apps used during testing
- Whether the machine has admin rights
- Whether this is a clean machine or an update from an older GlovU install

## Evidence To Collect

- Screenshot of install dialog
- Screenshot of UAC prompt
- Screenshot of tray icon
- Result notes for each test case
- `%APPDATA%\GlovU\glovu.log` if any failure occurs

## Test Cases

| ID | Scenario | Steps | Expected Result |
| --- | --- | --- | --- |
| W-01 | Clean first install | On a machine with no GlovU install, double-click `GlovU.exe` and click `Install` | Install dialog appears, UAC prompt appears, tray icon starts |
| W-02 | Declined install | On a clean machine, double-click `GlovU.exe` and cancel install or deny UAC | App exits cleanly, no broken proxy state, internet still works |
| W-03 | Relaunch after quit | Install GlovU, quit from the tray, then double-click `GlovU.exe` again | App starts again and tray icon returns |
| W-04 | Duplicate launch protection | While GlovU is already running, double-click `GlovU.exe` again | No second instance starts; user sees the already-running notice |
| W-05 | Quit cleanup | Start GlovU, then quit from the tray | Proxy is removed, internet still works normally, app exits |
| W-06 | Reboot / autostart | Install GlovU and reboot Windows | GlovU starts after login and protection returns without manual steps |
| W-07 | Update existing install | Start from a machine with an older GlovU install, then double-click the new `GlovU.exe` | Installed copy is refreshed and the new build runs |
| W-08 | Uninstall | Run the uninstall path and remove GlovU | App files are removed, autostart is removed, proxy is removed |
| W-09 | Port conflict | Occupy port `7777`, then start GlovU | App does not break internet; user gets a clear inactive-protection state |
| W-10 | AI browser flow | Use a supported browser with ChatGPT / Claude / Perplexity / DeepSeek | App stays running and does not unexpectedly quit |
| W-11 | Unknown app approval | Trigger AI traffic from a non-browser app | Approval / deny flow appears and persists decision |
| W-12 | Logging on failure | Force or observe an error, then inspect `%APPDATA%\GlovU\glovu.log` | A useful error trail exists for debugging |

## Pass Criteria

- `W-01` through `W-08` pass on at least 3 clean Windows machines
- `W-10` passes on at least 2 browser/app combinations
- No test leaves the machine with a stuck proxy after quit, failure, or uninstall
- All failures produce actionable log output

## Release Decision

- If all core tests pass: proceed with Windows paid beta / pilot distribution
- If install, quit cleanup, reboot, or update fails: do not broaden distribution
