"""Create a repeatable local-only ZenCore Field V33 showcase dataset.

Run with:
  /home/betopi/odoo/launch.sh 19 shell -d zencore_sp_clean_database \
    < zencore_salesperson_tracking/scripts/seed_local_showcase_odoo_shell.py

The script only replaces records carrying the ``ZENCORE_LOCAL_SHOWCASE_V33``
marker or the ``zc.local.demo.`` login prefix. It must never be used against a
production database.
"""
from datetime import timedelta

from odoo import Command, fields


MARKER = "ZENCORE_LOCAL_SHOWCASE_V33"
company = env.company
now = fields.Datetime.now()
today = fields.Date.context_today(env['res.users'])

Users = env['res.users'].sudo().with_context(
    active_test=False,
    no_reset_password=True,
    mail_create_nosubscribe=True,
    tracking_disable=True,
)
Plans = env['salesperson.visit.plan'].sudo().with_context(tracking_disable=True)
Trackers = env['salesperson.tracker'].sudo().with_context(tracking_disable=True)
Partners = env['res.partner'].sudo().with_context(tracking_disable=True)
Employees = env['hr.employee'].sudo().with_context(tracking_disable=True)
LocationLogs = env['salesperson.location.log'].sudo().with_context(tracking_disable=True)
Checkins = env['salesperson.checkin'].sudo().with_context(tracking_disable=True)
VisitedLines = env['salesperson.tracker.visited.line'].sudo().with_context(tracking_disable=True)
Sessions = env['salesperson.tracking.session'].sudo().with_context(tracking_disable=True)


# Idempotent cleanup: only local demo records, never normal users/data.
demo_users = Users.search([('login', '=like', 'zc.local.demo.%@example.invalid')])
demo_trackers = Trackers.search([('user_id', 'in', demo_users.ids)])
demo_plans = Plans.search(['|', ('user_id', 'in', demo_users.ids), ('internal_notes', 'ilike', MARKER)])
demo_trackers.unlink()
demo_plans.unlink()
Employees.search([('work_email', '=like', 'zc.local.demo.%@example.invalid')]).unlink()
Partners.search([('comment', 'ilike', MARKER)]).unlink()
demo_users.unlink()


def create_user(code, name, role, reports_to=False, job_title='Field Sales Executive'):
    login = 'zc.local.demo.%s@example.invalid' % code
    user = Users.create({
        'name': name,
        'login': login,
        'email': login,
        'phone': '+880 1700 %04d' % (1000 + len(code) * 31),
        'company_id': company.id,
        'company_ids': [Command.link(company.id)],
        'salesperson_role': role,
        'zc_reports_to_id': reports_to.id if reports_to else False,
        'group_ids': [Command.link(env.ref('base.group_user').id)],
    })
    Employees.create({
        'name': name,
        'user_id': user.id,
        'work_email': login,
        'company_id': company.id,
        'job_title': job_title,
    })
    return user


# 20 people: 1 CEO, 3 Managers, 4 Supervisors and 12 Salespeople.
ceo = create_user('ceo', 'Ayesha Rahman', 'ceo', job_title='Chief Executive Officer')
dhaka_manager = create_user('mgr_dhaka', 'Imran Hossain', 'manager', ceo, 'Regional Manager — Dhaka')
north_manager = create_user('mgr_north', 'Nabila Sultana', 'manager', ceo, 'Regional Manager — North')
south_manager = create_user('mgr_south', 'Rafiul Karim', 'manager', ceo, 'Regional Manager — South')

central_supervisor = create_user('sup_central', 'Sadia Islam', 'supervisor', ceo, 'Central Sales Supervisor')
gulshan_supervisor = create_user('sup_gulshan', 'Tanim Ahmed', 'supervisor', dhaka_manager, 'Gulshan Sales Supervisor')
north_supervisor = create_user('sup_north', 'Mehedi Hasan', 'supervisor', north_manager, 'North Sales Supervisor')
south_supervisor = create_user('sup_south', 'Rumana Akter', 'supervisor', south_manager, 'South Sales Supervisor')

sales_specs = [
    ('sales_01', 'Farhan Kabir', ceo, 'Key Account Salesperson'),
    ('sales_02', 'Maliha Noor', ceo, 'Key Account Salesperson'),
    ('sales_03', 'Rakibul Hasan', dhaka_manager, 'Dhaka Salesperson'),
    ('sales_04', 'Nusrat Jahan', dhaka_manager, 'Dhaka Salesperson'),
    ('sales_05', 'Arif Mahmud', gulshan_supervisor, 'Gulshan Salesperson'),
    ('sales_06', 'Tisha Sarker', gulshan_supervisor, 'Gulshan Salesperson'),
    ('sales_07', 'Sakib Chowdhury', gulshan_supervisor, 'Gulshan Salesperson'),
    ('sales_08', 'Samira Khan', north_manager, 'North Salesperson'),
    ('sales_09', 'Zubair Ahmed', north_manager, 'North Salesperson'),
    ('sales_10', 'Jannat Ara', north_supervisor, 'North Salesperson'),
    ('sales_11', 'Rasel Mia', north_supervisor, 'North Salesperson'),
    ('sales_12', 'Priyanka Das', south_supervisor, 'South Salesperson'),
]
salespeople = [create_user(code, name, 'salesman', manager, title)
               for code, name, manager, title in sales_specs]


# Customers span the Dhaka metro area so the maps and plan screens have useful
# names, coordinates and visit routes rather than zero-value placeholders.
customer_names = [
    'Apex Retail Gulshan', 'Bashundhara Traders', 'Banani Mart', 'Mirpur Distribution',
    'Uttara Wholesale Hub', 'Dhanmondi Super Store', 'Tejgaon Industrial Supply',
    'Mohammadpur Enterprise', 'Motijheel Business House', 'Farmgate Retail Point',
    'Khilgaon Grocery', 'Badda Consumer Store', 'Savar Trade Center', 'Gazipur Sales Hub',
    'Narayanganj Market Link', 'Jatrabari Supply Chain', 'Rampura Fashion House',
    'Kawran Bazar Foods', 'Baridhara Premium Shop', 'Purbachal New Market',
    'Keraniganj Trading Post', 'TongI Retail Network', 'Shyamoli Customer Point',
    'Wari Commercial House',
]
base_lat, base_lng = 23.7806, 90.4070
customers = []
for index, name in enumerate(customer_names):
    row, col = divmod(index, 6)
    customers.append(Partners.create({
        'name': name,
        'company_id': company.id,
        'customer_rank': 1,
        'phone': '+880 1800 %04d' % (2000 + index),
        'city': 'Dhaka',
        'street': 'Demo Road %s, Block %s' % (index + 1, chr(65 + col)),
        'partner_latitude': base_lat + (row - 1.5) * 0.012 + col * 0.0015,
        'partner_longitude': base_lng + (col - 2.5) * 0.012 + row * 0.0015,
        'comment': MARKER,
    }))


def add_route_logs(tracker, customer, mode, start):
    """Create a short, valid GPS route. ``mode`` drives dashboard status."""
    lat, lng = customer.partner_latitude, customer.partner_longitude
    if mode == 'idle':
        points = [(lat + 0.00001, lng + 0.00001), (lat + 0.000012, lng + 0.000013),
                  (lat + 0.000011, lng + 0.000012), (lat + 0.000012, lng + 0.000013)]
    elif mode == 'at_customer':
        points = [(lat - 0.003, lng - 0.003), (lat - 0.001, lng - 0.001),
                  (lat + 0.00005, lng + 0.00004), (lat + 0.00003, lng + 0.00002)]
    else:
        points = [(lat - 0.006, lng - 0.005), (lat - 0.004, lng - 0.003),
                  (lat - 0.002, lng - 0.001), (lat, lng)]
    for offset, (point_lat, point_lng) in enumerate(points):
        LocationLogs.create({
            'tracker_id': tracker.id,
            'tracked_at': start + timedelta(minutes=offset * 8),
            'latitude': point_lat,
            'longitude': point_lng,
            'accuracy': 8.0 + offset,
            'speed': 0.1 if mode == 'idle' else 4.2,
            'heading': 90.0,
            'source': 'local-showcase',
            'location_name': customer.name,
        })
    tracker._recalculate_verified_distance()


for index, salesperson in enumerate(salespeople):
    first_customer = customers[(index * 2) % len(customers)]
    second_customer = customers[(index * 2 + 1) % len(customers)]
    state = 'completed' if index < 4 else ('in_progress' if index < 7 else 'approved')
    plan = Plans.create({
        'user_id': salesperson.id,
        'visit_date': today,
        'purpose': ('order', 'followup', 'demo', 'payment')[index % 4],
        'priority': ('2' if index in (0, 5) else '1' if index % 3 == 0 else '0'),
        'state': state,
        'transport_cost': 280 + index * 15,
        'food_cost': 120 + index * 5,
        'other_cost': 30 if index % 2 else 0,
        'internal_notes': '%s — local showcase plan %02d' % (MARKER, index + 1),
        'target_line_ids': [
            Command.create({
                'sequence': 10,
                'customer_ids': [Command.link(first_customer.id)],
                'expected_time_minutes': 35,
                'expected_km': 4.2 + index * 0.2,
                'from_location': 'ZenCore Field Office',
                'to_location': first_customer.name,
                'notes': 'Product follow-up and stock review.',
            }),
            Command.create({
                'sequence': 20,
                'customer_ids': [Command.link(second_customer.id)],
                'expected_time_minutes': 40,
                'expected_km': 5.5 + index * 0.15,
                'from_location': first_customer.name,
                'to_location': second_customer.name,
                'notes': 'Order discussion and photo evidence capture.',
            }),
        ],
    })
    tracker_state = 'completed' if index < 4 else ('live' if index < 7 else 'planned')
    active = 4 <= index < 7
    last_seen = now - timedelta(minutes=index if active else 90 + index)
    tracker = Trackers.create({
        'user_id': salesperson.id,
        'sales_person': salesperson.name,
        'plan_id': plan.id,
        'visit_date': today,
        'priority': plan.priority,
        'state': tracker_state,
        'is_tracking': active,
        'last_seen': last_seen,
        'last_latitude': first_customer.partner_latitude,
        'last_longitude': first_customer.partner_longitude,
        'last_accuracy': 9.0,
        'location_name': first_customer.name,
        'transport_cost': plan.transport_cost,
        'food_cost': plan.food_cost,
        'other_cost': plan.other_cost,
        'actual_transport_cost': plan.transport_cost * 0.9,
        'actual_food_cost': plan.food_cost,
        'actual_other_cost': plan.other_cost,
        'total_tracking_time_seconds': 7200 + index * 180,
    })
    for plan_line in plan.target_line_ids:
        env['salesperson.tracker.target.line'].sudo().create({
            'tracker_id': tracker.id,
            'plan_line_id': plan_line.id,
            'expected_time_minutes': plan_line.expected_time_minutes,
            'expected_km': plan_line.expected_km,
            'customer_ids': [Command.set(plan_line.customer_ids.ids)],
            'from_location': plan_line.from_location,
            'to_location': plan_line.to_location,
            'notes': plan_line.notes,
        })

    route_mode = ('at_customer', 'moving', 'idle')[index - 4] if active else 'moving'
    route_start = now - timedelta(minutes=45 if active else 180 + index * 5)
    add_route_logs(tracker, first_customer, route_mode, route_start)

    Sessions.create({
        'tracker_id': tracker.id,
        'start_time': route_start,
        'end_time': False if active else route_start + timedelta(minutes=75),
        'state': 'active' if active else 'stopped',
        'last_location_lat': first_customer.partner_latitude,
        'last_location_lng': first_customer.partner_longitude,
    })

    if index < 4:
        for line_number, (plan_line, customer) in enumerate(zip(plan.target_line_ids, (first_customer, second_customer))):
            checkin_at = now - timedelta(hours=5 - line_number, minutes=index * 5)
            checkout_at = checkin_at + timedelta(minutes=28 + line_number * 7)
            checkin = Checkins.create({
                'tracker_id': tracker.id,
                'partner_id': customer.id,
                'target_line_id': plan_line.id,
                'location_name': customer.name,
                'checkin_time': checkin_at,
                'checkout_time': checkout_at,
                'checkin_latitude': customer.partner_latitude,
                'checkin_longitude': customer.partner_longitude,
                'checkout_latitude': customer.partner_latitude + 0.0001,
                'checkout_longitude': customer.partner_longitude + 0.0001,
                'state': 'checked_out',
                'notes': 'Completed showcase customer visit.',
                'meeting_outcome': 'positive' if line_number == 0 else 'followup',
            })
            VisitedLines.create({
                'tracker_id': tracker.id,
                'checkin_id': checkin.id,
                'partner_id': customer.id,
                'checkin_time': checkin_at,
                'checkout_time': checkout_at,
                'rating': '5' if line_number == 0 else '4',
            })
            plan_line.write({
                'is_visited': True,
                'actual_checkin_time': checkin_at,
                'actual_checkout_time': checkout_at,
                'actual_duration_minutes': (checkout_at - checkin_at).total_seconds() / 60.0,
            })
        tracker.write({
            'checkin_time': now - timedelta(hours=5),
            'checkout_time': now - timedelta(hours=3),
            'total_visit_time_minutes': 70.0,
        })

for role in ('salesman', 'supervisor', 'manager', 'ceo'):
    policy = env['zencore.approval.policy'].sudo().search([
        ('company_id', '=', company.id), ('role', '=', role)
    ], limit=1)
    if not policy:
        env['zencore.approval.policy'].sudo().create({
            'company_id': company.id,
            'role': role,
            'auto_approve': False,
            'active': True,
        })

env.cr.commit()
print('Created %s local showcase users, %s customers, %s plans and %s trackers.' % (
    len(salespeople) + 8, len(customers), len(salespeople), len(salespeople)
))
print('Marker: %s | Database: %s' % (MARKER, env.cr.dbname))
