# Login Fix: ZenCore Field V4

- Removed both native cookie-manager imports entirely. New app must be built and installed after dependency changes.
- No third-party native cookie package required. The platform fetch implementation is used instead; success is verified with `/web/session/get_session_info`.
- Never claim a login succeeds merely because `/web/session/authenticate` returned a uid. A second request must return the same user id.
- No plaintext credentials or cookies in diagnostic logs.
- HTML responses produce an HTTP/endpoint/final-URL error instead of `Unexpected character: <`.
- If session verification fails on your Odoo deployment, a dedicated secure token authentication bridge is a separate backend project. Do not hard-code passwords or session ids.

Quick checks:

```bash
npm ls @react-native-cookies/cookies @preeternal/react-native-cookie-manager
bash scripts/verify-login-fix.sh
npx tsc --noEmit
adb devices
npx expo run:android --device
```
