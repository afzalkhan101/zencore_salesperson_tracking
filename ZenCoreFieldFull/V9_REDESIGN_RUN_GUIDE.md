# ZenCore Field V9 — Gradient UI Redesign

## Scope
- Removes the Home **Quick Actions** section.
- Adds a branded blue-to-green gradient Home hero, an Open Tracking action, four KPI tiles, and a truthful Tracking Health section.
- Adds a matching gradient page banner to Visits, Tracking, Offline Sync, and Profile.
- Keeps V8 Visit Plan parity, local drafts, Odoo login, manager approval, GPS capture and manual sync business logic unchanged.
- No fabricated GPS routes and no changes to the Odoo addon backend in this release.

## Minimum developer environment (Ubuntu)
- Node 22+, JDK 17, configured Android SDK, Android device with USB Debugging or an emulator.
- Existing Expo SDK 58 project; use **development build**, not Expo Go for native GPS.

## Clean install (recommended to avoid editing the old running project)
```bash
mkdir -p ~/ZenCoreFieldV9
unzip ~/Downloads/ZenCoreField_V9_Gradient_Redesign.zip -d ~/ZenCoreFieldV9
cd ~/ZenCoreFieldV9/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
adb devices -l
npx expo prebuild --platform android --clean
npx expo run:android --device
```
Note: `prebuild --clean` regenerates the native Android directory. The ZIP intentionally contains source only and no pre-built native build outputs.

## Metro (after native build)
```bash
cd ~/ZenCoreFieldV9/ZenCoreFieldFull
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```
Only run one Metro server at a time, from the V9 folder. Open the installed ZenCore Field development app, not Expo Go.

## Verification checklist
1. Home: Confirm **Quick Actions** is absent.
2. Home: Confirm blue/teal/green gradient and **Open Tracking** button.
3. Home: KPI tiles reflect existing Odoo plan data. Tracking Health must show the *actual* session state.
4. Open Tracking: same tracking screen and existing plan-specific start/stop logic as V8.
5. Visit Plans: list, create, edit target lines, expenses, submit, approval refresh.
6. Sync: the same queued GPS counts and manual Sync action.
7. Profile: the same HTTPS Odoo login function.
8. Confirm there are no runtime errors on a physical Android device. Test on a physical iPhone before iOS release.

## Known limitations
- A successful TypeScript syntax check is not equivalent to a native APK or iOS build.
- This release changes visual presentation, not GPS reliability or routing architecture.
- `expo-linear-gradient` is a *new native Expo dependency*; rebuild the native app rather than only refreshing Metro.
- The current Home **Open Tracking** action navigates to the Tracking screen. It **does not automatically start the first approved plan**; that feature needs separate business-logic development and validation.
- Live map remains a placeholder, and offline GPS requires a running native background session with correct permissions.
- The Odoo bridge is included from V8 for convenience. You need not upgrade the server solely for these UI changes if the existing V8 API is already working.
