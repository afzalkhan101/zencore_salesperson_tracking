from pathlib import Path
import re,urllib.parse,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
a=(root/'odoo_addon/zencore_salesperson_tracking/static/src/img/walking_salesperson_briefcase.svg').read_text().strip()
ET.fromstring(a)
mobile=(root/'src/components/LiveRouteMap.tsx').read_text()
encoded=re.search(r'data:image/svg\+xml,([^"\s]+)',mobile)
assert encoded, 'mobile inline SVG data URL missing'
assert urllib.parse.unquote(encoded.group(1))==a, 'Mobile and Odoo SVG assets diverged'
move=(root/'odoo_addon/zencore_salesperson_tracking/static/src/js/templates.js').read_text()
dash=(root/'odoo_addon/zencore_salesperson_tracking/static/src/js/dashboard_live_map.js').read_text()
for value in (move,dash):
 assert '/static/src/img/walking_salesperson_briefcase.svg' in value
assert 'border-radius:50%;background:' not in move[move.index("className: 'zc-salesperson-endpoint'"):][:600]
assert '🚶‍♂️💼' not in mobile and '🚶‍♂️💼' not in move
assert 'zc-walker-active' in dash and 'zc-walker-inactive' in dash
print('PASS: same SVG artwork in all three maps; no round emoji badge')
