> V10 stable gradient UI: read `V10_RUN_AND_TROUBLESHOOT.md` first. This patch requires no Odoo module upgrade.

# ZenCore Field V8 — Visit Plan Parity

React Native + TypeScript / Expo Development Build client for Odoo 19 Salesperson Tracking.

**Start here: [V8_INSTALL_AND_TEST.md](V8_INSTALL_AND_TEST.md)**

Version V8 adds a four-step Visit Plan editor covering all fields visible on the original Odoo plan form: Salesperson, Visit Date, Purpose, Priority, Total Visits, target line minutes, accompanies, locations, KM, multiple customers and notes, plus expenses and review/submit. Odoo computes totals and retains manager approval.

Includes `odoo_addon/zencore_field_mobile_bridge` **19.0.5.0.0** which must be installed/upgraded in Odoo.sh staging *before* testing mobile create and detail APIs. Existing `zencore_salesperson_tracking` remains intact.

Odoo login uses platform HTTP session handling rather than the old native cookie-manager dependency. Live GPS/background sync still has the pre-existing operational limitations described in the guides. Current project source is not an independently verified release build.
