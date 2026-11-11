# Run deliberately in an Odoo.sh STAGING Odoo shell only.
# Requires: ZENCORE_SEED_CONFIRM = 'I_UNDERSTAND_STAGING_ONLY'
# Does not change existing users; no passwords or GPS records are created.
from odoo import fields, Command

if globals().get('ZENCORE_SEED_CONFIRM') != 'I_UNDERSTAND_STAGING_ONLY':
    raise RuntimeError('Refusing to seed data: set ZENCORE_SEED_CONFIRM in the Odoo shell first.')

company = env.company
Users = env['res.users'].sudo().with_context(no_reset_password=True, mail_create_nosubscribe=True, tracking_disable=True)
Partners = env['res.partner'].sudo().with_context(tracking_disable=True)
Policies = env['zencore.approval.policy'].sudo().with_context(tracking_disable=True)
Plans = env['salesperson.visit.plan'].sudo().with_context(tracking_disable=True)

def get_user(code, name, role, parent=None):
    login = 'zc.demo.' + code + '@example.invalid'
    found = Users.search([('login', '=', login)], limit=1)
    if found:
        # Safety: never modify a previously existing login.
        if found.name != name or found.salesperson_role != role or (parent and found.zc_reports_to_id != parent):
            raise RuntimeError('Conflicting existing demo user login: ' + login)
        return found
    vals = {'name':name,'login':login,'salesperson_role':role,'company_id':company.id,
            'company_ids':[Command.link(company.id)], 'group_ids':[Command.link(env.ref('base.group_user').id)]}
    if parent:
        vals['zc_reports_to_id'] = parent.id
    return Users.create(vals)

ceo = get_user('ceo','Demo CEO','ceo')
ceo_alt = get_user('ceo_alt','Demo CEO Alternate','ceo')
north = get_user('mgr_north','Demo Manager North','manager',ceo)
south = get_user('mgr_south','Demo Manager South','manager',ceo)
sup_north = get_user('sup_north','Demo Supervisor North','supervisor',north)
sup_south = get_user('sup_south','Demo Supervisor South','supervisor',south)
sales_a = get_user('sales_a','Demo Salesperson A','salesman',sup_north)
sales_b = get_user('sales_b','Demo Salesperson B','salesman',sup_north)
sales_c = get_user('sales_c','Demo Salesperson C','salesman',sup_south)

customers = {}
for key,name,city in [('a','ZenCore Demo Customer Alpha','Dhaka'),('b','ZenCore Demo Customer Beta','Dhaka'),('c','ZenCore Demo Customer Gamma','Gazipur')]:
    p = Partners.search([('name','=',name),('company_id','in',[False,company.id])],limit=1)
    customers[key] = p or Partners.create({'name':name,'city':city,'customer_rank':1})

for role in ('salesman','supervisor','manager','ceo'):
    if not Policies.search([('company_id','=',company.id),('role','=',role)],limit=1):
        Policies.create({'company_id':company.id,'role':role,'auto_approve':False})

specs=[('sales_a',sales_a,'a','followup','0'),('sales_b',sales_b,'b','demo','1'),
       ('sales_c',sales_c,'c','order','1'),('sup_north',sup_north,'a','followup','0'),
       ('mgr_north',north,'b','payment','1'),('mgr_south',south,'c','complaint','0')]
for key,user,customer,purpose,priority in specs:
    marker = 'ZENCORE V20 DEMO ' + key
    exists = Plans.search([('user_id','=',user.id),('internal_notes','ilike',marker)],limit=1)
    if exists:
        continue
    Plans.create({
        'user_id':user.id, 'visit_date':fields.Date.context_today(Plans), 'purpose':purpose,
        'priority':priority,'internal_notes':marker,
        'target_line_ids':[Command.create({
            'customer_ids':[Command.link(customers[customer].id)],
            'expected_time_minutes':30, 'expected_km':5.0,
            'from_location':'ZenCore Demo Office','to_location':'Customer Location',
            'notes':'Demo UAT target; simulated only.'
        })],
    })
env.cr.commit()
print('Created/verified ZenCore hierarchy demo records for company:', company.display_name)
print('Logins: zc.demo.<role>@example.invalid; passwords NOT set. Assign test passwords manually as admin.')
print('6 draft Visit Plans ready; switch policies in Approval Configuration to test manual/auto approval.')
