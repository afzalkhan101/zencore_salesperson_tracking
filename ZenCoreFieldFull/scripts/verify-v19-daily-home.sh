#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
grep -q 'ZENCORE_FIELD_V19_DAILY_WORKSPACE' App.tsx
grep -q 'fieldTodaySummary' App.tsx
grep -q 'Next Customer Visit' App.tsx
grep -q 'Today.s Visit Schedule' App.tsx
grep -q '/zencore/field/v7/home/today' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
python3 -m py_compile odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
echo 'V19 source and Python checks passed'
