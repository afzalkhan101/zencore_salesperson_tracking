# Acceptance test plan — required before field deployment

1. Android physical phone screen-locked 60+ minutes; verify captured timestamps and count.
2. iPhone physical device background, location permission variations, OS termination; characterize gaps, do not fabricate paths.
3. Airplane mode 30+ minutes, then internet recovery; verify SQLite retention; current manual Sync and Bridge UUID receipts documented.
4. Stop and restart sessions; verify map does not connect across idle gap.
5. Accuracy outdoors/indoors; distinguish raw GPS distance from validated travel distance.
6. Odoo manager approve, rejection, plan state transitions; mobile cannot submit draft with empty real customer IDs.
7. Visit expenses must match Odoo and preserve multi-target data after backend update.
8. Check-in/out authorization, geofence, location spoofing considerations and audit logs.
9. Privacy policy, tracking consent, business-hours controls, data retention / delete workflows.
10. Offline photo storage, checksums, upload ACK and after-relaunch persistence (not yet implemented).

**No APK/IPA was built/tested in this environment.** Native build and physical device test remain outstanding.
