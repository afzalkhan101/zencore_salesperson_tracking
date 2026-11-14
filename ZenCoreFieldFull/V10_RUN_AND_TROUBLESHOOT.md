# ZenCore Field V10 — Stable Gradient UI

## Why the phone previously displayed blank white
The previously installed Android development APK did not include the ExpoLinearGradient native ViewManager. JavaScript from V9 tried to render that native component. V10 replaces expo-linear-gradient with bundled PNG gradients displayed by React Native core Image. This removes that specific native dependency and should avoid the corresponding ViewManager error. A blank screen can have other causes: check Metro/adb logs if it persists.

## Odoo.sh
**No Odoo addon deploy or upgrade is required for this UI-only change.** Keep the existing `zencore_field_mobile_bridge` addon installed in the Odoo 19 database. Only deploy/upgrade the addon if backend changes are explicitly made in a later release. This ZIP includes the V8-era addon for reference, but it has not been changed by V10.

## Ubuntu fresh-install instructions (recommended to prevent stale bundles)

1. Stop any old Metro terminal with Ctrl+C. Only one Expo project should serve port 8081.
2. Extract the V10 ZIP into a *new folder*, not on top of an older project.

```bash
cd ~
mkdir -p ZenCoreFieldV10
unzip ~/Downloads/ZenCoreField_V10_Stable_Gradient_NoNativeCrash.zip -d ~/ZenCoreFieldV10
cd ~/ZenCoreFieldV10/ZenCoreFieldFull
node -v                         # Node 22 expected
npm install
bash scripts/verify-v10-ui.sh
npx expo install --check
npx tsc --noEmit
npx expo config --type public
adb devices -l
```

3. Physical phone must show status `device`. Build and install on that phone:

```bash
npx expo prebuild --platform android --clean
npx expo run:android --device 4PU8QGBUOFFYGUH6
```

If an interactive device selection menu appears, select the physical device and **press Enter**. `Ctrl+C` cancels the build. Wait for the Gradle build/install to finish. The ADB serial above came from previous logs; verify it is still correct with `adb devices -l`.

4. If you want to bypass the device selector, after prebuild use:

```bash
cd android
./gradlew :app:installDebug -PreactNativeDevServerPort=8081
cd ..
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

5. Open the **ZenCore Field** app on the phone. Expo Go is not a substitute for the development build.

## Check stale project / competing Metro server

```bash
pwd
grep -n 'GradientBackground' App.tsx
grep -n 'Quick Actions' App.tsx
sudo lsof -nP -iTCP:8081 -sTCP:LISTEN
adb logcat -d -s ReactNativeJS:E ReactNative:E | tail -100
```

Expected: V10 project root, GradientBackground imports, no Quick Actions heading. If the app stays blank after a successful install, capture the first runtime error (not only the last stack frame).

## Odoo Login / Visit Plan
Do not reset or delete the Odoo database. Existing Odoo session, plan approval, and plan-wise tracking API are unchanged by V10. Verify with Profile > Odoo Login then Visits > Refresh Odoo Plans. The app can display 0 plans if its session is not verified or list has not been refreshed; that is not proof the database contains no plans.

## Known limitations
- Not possible to certify Android/iOS device builds from this package alone; run the commands above on a real phone.
- Native background GPS, offline sync reliability, live map, and photo upload need separate end-to-end testing.
- No server-side Odoo fixes are included in this UI-only patch.
