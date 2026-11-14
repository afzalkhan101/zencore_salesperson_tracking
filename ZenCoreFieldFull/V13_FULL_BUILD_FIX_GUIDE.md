# ZenCore Field V13 — Full Build Fix (Android / Ubuntu)

This is the entire V13 mobile source and Odoo bridge, with the missing React Native `Image` import fixed and a fresh-build helper. It is **not** a new GPS algorithm or a verified production release.

## What caused your errors?

1. `TS2786: Image cannot be used as a JSX component`: `App.tsx` used `<Image>` without importing `Image` from `react-native`; TypeScript selected the global HTML Image constructor instead.
2. `verify-v13-tracking.sh not found`: The terminal was in a project directory without the V13 script. This archive includes it.
3. Gradle's `.../.local/share/Trash/files/ZenCoreFieldFull.15/...` references and missing NetInfo native source suggest a stale/moved project build or incomplete dependencies. Do not build from Trash or copy its `android/` and `node_modules/` directories.

## Prepare Ubuntu

Use Node.js 22+, JDK 17, Android Studio with Android SDK, platform tools (`adb`), and a USB-debugging-enabled device. Set `ANDROID_HOME=$HOME/Android/Sdk`, `JAVA_HOME` to your JDK path, and SDK platform-tools in PATH as needed.

## Fresh extraction, installation, typecheck and native regeneration

```bash
mkdir -p ~/ZenCoreFieldV13Fixed
unzip ~/Downloads/ZenCoreField_V13_Full_BuildFix.zip -d ~/ZenCoreFieldV13Fixed
cd ~/ZenCoreFieldV13Fixed/ZenCoreFieldFull
bash scripts/install-and-build-v13-fixed.sh
```

**Run commands from this exact directory, not `~/ZenCoreFieldFull` unless you have deliberately copied all V13 files there.** Run `pwd -P` to verify.

## Build on device

```bash
cd ~/ZenCoreFieldV13Fixed/ZenCoreFieldFull
adb devices -l
npx expo run:android --device YOUR_DEVICE_SERIAL
```

For the previously shown OPPO device, the observed serial was `4PU8QGBUOFFYGUH6` (use the current value from `adb devices`). If prompted to choose the device, highlight it and press **Enter**, not Ctrl+C. Wait for successful APK installation.

In another terminal, run:

```bash
cd ~/ZenCoreFieldV13Fixed/ZenCoreFieldFull
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

Stop any other Metro instance on port 8081 before starting it. Do not uninstall the current app or clear its storage: there may be pending SQLite GPS data. The Android package is `com.zencore.field`; installing over an existing app will preserve data only if the signing keys are compatible. If they are not, do **not** uninstall until pending data is recovered or synced.

## Verification

```bash
pwd -P
bash scripts/verify-v13-tracking.sh
npx tsc --noEmit
test -d node_modules/@react-native-community/netinfo/android && echo 'NetInfo OK'
grep -n "View,Image}" App.tsx
```

The script is a structural check, not proof of GPS sync. In the app, test Odoo login → approved plan → Start Tracking → verify Plan ID and Tracker ID → collect GPS → Stop Tracking → verify auto-sync acknowledgement and Location Data in Odoo.

## Odoo.sh

This repair only fixes mobile source/build packaging. Do **not** upgrade the Odoo addon solely for these fixes if the existing V13-compatible `zencore_field_mobile_bridge` APIs already work. The addon is included in `odoo_addon/` for reference or deployment on staging when needed. Never replace the original `zencore_salesperson_tracking` with this bridge.

## If build fails

Run `pwd -P`, `readlink -f android`, and `ls -ld node_modules/@react-native-community/netinfo/android`. Capture the first `* What went wrong:` error and avoid mixing builds from the Trash project. Full native Android and Odoo integration tests are not performed in this packaging environment.
