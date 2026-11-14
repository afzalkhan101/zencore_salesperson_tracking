# Odoo 19 module comparison (source verified)

Inspected `zencore_salesperson_tracking_auto_distance_odoo19.zip` source: `controllers/mobile_api.py`, `controllers/main.py`, `models/salesperson_visit_plan.py`, `models/salesperson_visit_plan_line.py`.

| Odoo | Existing route / fields | Mobile implementation | Gap |
|---|---|---|---|
| Plans | GET `/mobile/api/plans` | Fetch server plans | No full detail/expenses payload |
| Customer search | GET `/mobile/api/partners/search?q=` | Search/select real IDs | Uses session auth; limit 20 |
| Plan creation | Original POST `/mobile/api/plans/create` | App uses included Bridge `/zencore/field/v2/plans` | Bridge preserves multiple target lines, priority, expenses; coordinate geocoding still pending |
| Drafts | `salesperson.visit.plan` state draft, `action_submit` | Locally stored drafts in SQLite | Bridge supports server draft creation, but app currently stores draft locally before server submit |
| Target lines | `customer_ids`, `from_location`, `to_location`, `expected_km`, lat/lng | UI fields and local preservation | Add API for multiple lines, autocomplete and route cost |
| Expenses | `transport_cost`, `food_cost`, `other_cost`, computed `total_cost` | Bridge create submits amounts with plan | Editing/reconciling actual expense claims after approval needs additional API |
| Today tracker | GET `/mobile/api/tracker/today` | Fetch tracker ID | Some planned tracking sessions need backend action-on-track coordination |
| Tracking start/stop | POST `/salesperson_tracking/start` and `/stop` | Native tracking coordinated with server | Validate server-side user ownership of `tracker_id` |
| GPS | Original POST `/salesperson_tracking/mobile/ping` | Bridge `/zencore/field/v2/gps/batch`, SQLite and manual batch sync | Bridge UUID receipts cover replays; offline logs do not update calculated distance and real-time last position |
| Customers per plan | GET `/mobile/api/plans/<id>/customers` | Renders customer cards | Endpoint lacks plan ownership check before `sudo()` |
| Check-in/out | POST `/mobile/api/checkin` and `/mobile/api/checkout/<id>` | GPS-aware buttons | Checkout ownership check required; photo save not implemented in app |
| Visit photos | `selfie` base64 in check-in/out; `/mobile/api/screenshot` | Camera/gallery only | Consent, file persistence, checksums, retry queue, secure upload |
| Dashboard | GET `/mobile/api/dashboard` | Not yet wired | Response mapping required |

## Backend changes needed before production
- Security audit of `sudo()` controller methods; check authenticated user's own plans, trackers, customers and checkins.
- Token auth with device enrollment, short-lived access and refresh / revocation (not relying on fragile cookie extraction).
- Bridge currently supports plan creation with target lines, priority and expenses. Editing existing plans, geocoded coordinate routing, and offline photo uploading need additional endpoints.
- Bridge currently ingests batch GPS by device UUID and tracker ownership with per-point acknowledgements, preserving capture time for delayed records. Add server session association and distance recomputation rules.
- Durable image attachment upload with idempotency, size limits and per-visit association.
- Offline status visibility in manager dashboard based on GPS capture time versus receive time.
- Timezone-safe date handling and tracking session discontinuity on map.
