# ZenCore Field V14.1 — Image Render Fix

## Corrected issue
`ReferenceError: Property 'Image' doesn't exist` in `App.tsx` photo preview. The updated source uses `Image as RNImage` imported from `react-native`, and `<RNImage>` for previews. The old V14 archive already contained an `Image` import, so a stale or mixed Metro source is another possible cause. This package includes a unique startup marker to verify the new bundle.

## Installation on Ubuntu (new folder)

```bash
mkdir -p ~/ZenCoreFieldV14_1
unzip ~/Downloads/ZenCoreField_V14_1_Image_Render_Fix.zip -d ~/ZenCoreFieldV14_1
cd ~/ZenCoreFieldV14_1/ZenCoreFieldFull
pwd
npm install
bash scripts/verify-v14-1-image-fix.sh
npx tsc --noEmit
```

Close any Metro server in other terminals (Ctrl+C). Check which process uses port 8081 with `lsof -nP -iTCP:8081 -sTCP:LISTEN`. Start Metro **only from the new V14.1 directory**:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

Open the installed ZenCore Field development app and look in the Metro output for:

`[ZenCore Build] ZENCORE_FIELD_V14_1_IMAGE_RENDER_FIXED`

If the existing development APK cannot load this JS or native packages differ, build and install from the V14.1 directory:

```bash
adb devices -l
npx expo run:android --device
```

Select the phone and press Enter. This JavaScript-only Image fix normally does not need a native rebuild when the same native dependencies are already installed.

## Testing
1. Open Odoo Profile, confirm login.
2. Open Visits > an approved plan (e.g., plan 59).
3. Open Visit Photos & Chatter Evidence. The screen should render without `Image` ReferenceError.
4. Use Take Photo or Gallery, inspect image preview.
5. Check Pending/Uploaded after auto upload, and inspect Chatter on the same Odoo Visit Plan. The Odoo bridge must already be deployed for uploads to succeed.

## Odoo.sh
No Odoo.sh update is necessary **for this rendering-only fix**, provided V14 `zencore_field_mobile_bridge` already exists and its photo endpoint works. If not, deploy the included addon to staging and upgrade it before testing photo uploads.

## Caution
Do not uninstall the mobile app or clear its storage to fix this JSX issue: offline photos and unsynced GPS data may be lost. Avoid blindly replacing the complete current working project without backing it up. Real-device runtime and live Odoo photo upload are not verified in this environment.
