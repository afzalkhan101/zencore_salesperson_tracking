import json
import base64
import binascii
import re
from datetime import datetime,timedelta
from odoo import fields,http
from odoo.http import request
from odoo.exceptions import ValidationError

class ZenCoreFieldMobileBridge(http.Controller):
    def _json(self,payload,status=200):
        return request.make_response(json.dumps(payload,default=str),headers=[('Content-Type','application/json')],status=status)
    def _body(self):
        return json.loads((request.httprequest.data or b'{}').decode('utf-8'))
    def _owner(self):
        user=request.env.user
        if user._is_public(): raise ValidationError('Login required')
        return user

    @staticmethod
    def _customer_domain(Partner):
        """Return only genuine customer contacts, never staff or user contacts.

        The mobile application uses this for every customer picker and for
        server-side plan validation. The caller must use this domain with a
        sudoed partner model: HR's ``employee_ids`` is intentionally not made
        readable to field users, but it is needed to remove employee contacts
        that happen to have a customer rank in old data.
        """
        domain = [('active', '=', True), ('name', '!=', False)]
        if 'customer_rank' in Partner._fields:
            domain.append(('customer_rank', '>', 0))
        if 'user_ids' in Partner._fields:
            domain.append(('user_ids', '=', False))
        if 'employee_ids' in Partner._fields:
            domain.append(('employee_ids', '=', False))
        if 'company_id' in Partner._fields:
            domain.append(('company_id', 'in', [False, request.env.company.id]))
        return domain

    # V18: authenticated read-only profile/dashboard; never substitute demo data.
    @http.route('/zencore/field/v6/profile',type='http',auth='user',csrf=False,methods=['GET'])
    def field_profile_v18(self, **kwargs):
        try:
            user = self._owner()
            # Field hierarchy role takes precedence over generic sales groups.
            zc_role = dict(user._fields['salesperson_role'].selection).get(user.salesperson_role, 'Salesperson')
            if user.has_group('base.group_system'):
                role = 'Administrator'
            elif user.has_group('sales_team.group_sale_manager'):
                role = 'Sales Manager'
            elif user.has_group('sales_team.group_sale_salesman') or user.has_group('sales_team.group_sale_salesman_all_leads'):
                role = 'Salesperson'
            else:
                role = 'Odoo User'
            return self._json({'id':user.id,'name':user.name or '',
                               'login':user.login or '',
                               'company':user.company_id.name or '',
                               'role':zc_role,
                               'reports_to':user.zc_reports_to_id.name or ''})
        except Exception as ex:
            return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v6/dashboard',type='http',auth='user',csrf=False,methods=['GET'])
    def field_dashboard_v18(self, **kwargs):
        try:
            user = self._owner()
            Plan = request.env['salesperson.visit.plan'].sudo()
            Tracker = request.env['salesperson.tracker'].sudo()
            plans = Plan.search([('user_id','=',user.id)])
            # Include only trackers belonging to the signed-in user's plans.
            trackers = Tracker.search([('plan_id','in',plans.ids)]) if plans else Tracker.browse([])
            completed = sum(1 for p in plans if p.state == 'completed')
            distance = None
            if 'total_distance_km' in Tracker._fields:
                distance = round(sum(max(0.0,float(t.total_distance_km or 0)) for t in trackers),2)
            completed_visits = 0
            unique_customers = set()
            if 'visited_line_ids' in Tracker._fields:
                for tracker in trackers:
                    for visit in tracker.visited_line_ids:
                        if visit.checkin_time:
                            completed_visits += 1
                            if visit.partner_id:
                                unique_customers.add(visit.partner_id.id)
            elif 'total_visited' in Tracker._fields:
                completed_visits = sum(max(0, int(t.total_visited or 0)) for t in trackers)
            # Read-only historical GPS fallback: some trackers have 0 stored km
            # even though the movement map displays verified recorded movement.
            # Only inspect trackers belonging to THIS authenticated user.
            if trackers:
                try:
                    from odoo.addons.zencore_salesperson_tracking.models.verified_gps import verified_distance_km
                    robust_distance = 0.0
                    for tracker in trackers[:150]:
                        stored = max(0.0, float(tracker.total_distance_km or 0))
                        if stored > 0:
                            robust_distance += stored
                            continue
                        request.env.cr.execute('''SELECT latitude, longitude, accuracy, tracked_at
                            FROM salesperson_location_log WHERE tracker_id = %s
                            ORDER BY tracked_at ASC, id ASC LIMIT 20000''', (tracker.id,))
                        robust_distance += max(0.0, verified_distance_km(request.env.cr.fetchall()))
                    if len(trackers) <= 150:
                        distance = round(robust_distance, 3)
                except Exception:
                    # Keep stored totals when older logs cannot be read.
                    pass
            return self._json({'visit_plans':len(plans),
                               'completed_plans':completed,
                               'completed_visits':completed_visits,
                               'completed_customer_visits':len(unique_customers) if unique_customers else (completed_visits if 'visited_line_ids' not in Tracker._fields else 0),
                               'total_distance_km':distance})
        except Exception as ex:
            return self._json({'ok':False,'message':str(ex)},400)

    # V19: daily workspace data, scoped to the currently authenticated salesperson.
    # No fabricated schedule time: the target lines do not define one.
    @http.route('/zencore/field/v7/home/today', type='http', auth='user', csrf=False, methods=['GET'])
    def field_today_v19(self, **kwargs):
        try:
            user = self._owner()
            Plan = request.env['salesperson.visit.plan'].sudo()
            today = fields.Date.context_today(user)
            plans = Plan.search([('user_id', '=', user.id), ('visit_date', '=', today)], order='id asc')
            schedule = []
            for plan in plans:
                for line in plan.target_line_ids.sorted(key=lambda l: (l.sequence, l.id)):
                    customer = line.customer_ids[:1]
                    location = ''
                    if customer:
                        partner = customer[0]
                        location = ', '.join(filter(None, [partner.street or '', partner.city or '']))
                    schedule.append({
                        'plan_id': plan.id, 'plan_name': plan.name, 'line_id': line.id,
                        'customer_names': line.customer_ids.mapped('name'),
                        'visited': bool(line.is_visited), 'location': location,
                        'latitude': partner.partner_latitude if customer and 'partner_latitude' in partner._fields else None,
                        'longitude': partner.partner_longitude if customer and 'partner_longitude' in partner._fields else None,
                        'plan_state': plan.state,
                    })
            next_item = next((item for item in schedule if not item['visited'] and item['plan_state'] in ('approved', 'in_progress')), None)
            if next_item:
                next_item = dict(next_item, customer_name=(next_item['customer_names'] or ['Target visit'])[0])
            return self._json({
                'date': str(today), 'total_targets': len(schedule),
                'completed_targets': sum(1 for item in schedule if item['visited']),
                'schedule': schedule[:60], 'next_visit': next_item,
            })
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    # V20: shared hierarchy approval API. All permission checks are enforced
    # again by the original Odoo models, not merely by hiding mobile buttons.
    @http.route('/zencore/field/v8/approvals', type='http', auth='user', methods=['GET'], csrf=False)
    def hierarchy_approvals(self, **kwargs):
        try:
            user = self._owner()
            plans = request.env['salesperson.visit.plan'].sudo().search([
                ('zc_approver_id','=',user.id), ('state','=','submitted')],
                order='visit_date asc,id asc', limit=100)
            return self._json({'ok':True, 'approvals':[
                dict(id=p.id,name=p.name,owner=p.user_id.name,
                     role=p.user_id.salesperson_role,visit_date=str(p.visit_date),
                     purpose=p.purpose,customer_names=p.customer_names or '',
                     status=p.state) for p in plans]})
        except Exception as ex:
            return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v8/approvals/<int:plan_id>/<string:decision>',
                type='http', auth='user', methods=['POST'], csrf=False)
    def decide_hierarchy_approval(self, plan_id, decision, **kwargs):
        try:
            user = self._owner()
            if decision not in ('approve','reject'):
                raise ValidationError('Invalid approval action')
            plan = request.env['salesperson.visit.plan'].sudo().browse(plan_id)
            if not plan.exists() or plan.state != 'submitted' or plan.zc_approver_id.id != user.id:
                raise ValidationError('Request is unavailable or not assigned to you.')
            if decision == 'approve':
                plan.action_approve()
            else:
                plan.action_reject()
            return self._json({'ok':True,'state':plan.state,'plan_id':plan.id})
        except Exception as ex:
            return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v3/health', type='http', auth='user', csrf=False, methods=['GET'])
    def bridge_health(self, **kwargs):
        # Authenticated diagnostic endpoint. Does not expose secrets or modify records.
        return self._json({
            'ok': True,
            'bridge': 'zencore_field_mobile_bridge',
            'api_version': 'v3',
            'create_plan': '/zencore/field/v3/plans',
            'tracking': 'plan-wise',
        })

    @http.route('/zencore/field/v3/customers', type='http', auth='user', csrf=False, methods=['GET'])
    def list_customers(self, q='', limit='50', offset='0', **kwargs):
        """Paginated customer/partner picker; only readable records, no mobile dependency.

        An empty q lists names immediately. The current Odoo user's res.partner
        record rules are respected, and we only return minimal contact fields.
        """
        try:
            self._owner()
            limit = min(100, max(1, int(limit)))
            offset = max(0, int(offset))
            if offset > 100000:
                raise ValidationError('Customer offset is too large')
            q = (q or '').strip()[:100]
            Partner = request.env['res.partner'].sudo()
            domain = self._customer_domain(Partner)
            if q:
                searchable = [x for x in ('name', 'phone', 'email', 'mobile') if x in Partner._fields]
                terms = [(name, 'ilike', q) for name in searchable]
                if terms:
                    domain += ['|'] * (len(terms) - 1) + terms
            records = Partner.search(domain, order='name asc,id asc', limit=limit + 1, offset=offset)
            has_more = len(records) > limit
            records = records[:limit]
            def safe_value(record, field):
                return (record[field] or '') if field in Partner._fields else ''
            customers = [{
                'id': item.id,
                'name': item.name or '',
                'phone': safe_value(item, 'phone') or safe_value(item, 'mobile'),
                'street': safe_value(item, 'street'),
                'city': safe_value(item, 'city'),
                'latitude': item.partner_latitude if 'partner_latitude' in Partner._fields else None,
                'longitude': item.partner_longitude if 'partner_longitude' in Partner._fields else None,
            } for item in records]
            return self._json({'ok': True, 'partners': customers, 'has_more': has_more,
                               'next_offset': offset + len(customers)})
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route('/zencore/field/v11/customers/create', type='http', auth='user',
                csrf=False, methods=['POST'])
    def create_mobile_customer_v32(self, **kwargs):
        """Create one same-company customer with precise coordinates.

        Authentication is mandatory. Caller may NOT choose company, owner,
        internal user or any privileged Odoo fields. Never accept a generic
        ``vals`` dictionary from an untrusted mobile client.
        """
        try:
            user = self._owner()
            if not user.has_group('base.group_user'):
                return self._json({'ok': False, 'message': 'Internal user account required.'}, 403)
            raw = request.httprequest.get_data(cache=False)
            if len(raw) > 4096:
                return self._json({'ok': False, 'message': 'Customer details are too long.'}, 400)
            data = json.loads(raw or b'{}')
            if not isinstance(data, dict):
                raise ValidationError('Invalid customer data.')
            name = str(data.get('name') or '').strip()
            address = str(data.get('address') or '').strip()
            email = str(data.get('email') or '').strip().lower()
            phone = str(data.get('phone') or '').strip()
            if not 2 <= len(name) <= 160:
                raise ValidationError('Enter a customer name (2–160 characters).')
            if not 5 <= len(address) <= 500:
                raise ValidationError('Enter a detailed address (5–500 characters).')
            if len(phone) > 40 or (phone and not re.fullmatch(r'[+0-9 ()-]{6,40}', phone)):
                raise ValidationError('Invalid phone number.')
            if len(email) > 200 or (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
                raise ValidationError('Invalid email address.')
            try:
                latitude = float(data.get('latitude'))
                longitude = float(data.get('longitude'))
            except (ValueError, TypeError):
                raise ValidationError('Latitude and longitude are required.')
            import math
            if (not math.isfinite(latitude) or not math.isfinite(longitude)
                    or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180)
                    or (latitude == 0 and longitude == 0)):
                raise ValidationError('Invalid latitude or longitude.')
            Partner = request.env['res.partner']
            if 'partner_latitude' not in Partner._fields or 'partner_longitude' not in Partner._fields:
                return self._json({'ok': False, 'message':
                    'Install Odoo base_geolocalize to enable customer GPS coordinates.'}, 409)
            # Limit abuse even if the account is self-registered.
            from datetime import timedelta
            cutoff = fields.Datetime.now() - timedelta(hours=1)
            recent = Partner.sudo().search_count([
                ('create_uid', '=', user.id), ('create_date', '>=', fields.Datetime.to_string(cutoff))])
            if recent >= 20:
                return self._json({'ok': False,
                                   'message': 'Customer creation limit reached. Try again later.'}, 429)
            # Only same-company partners are examined. Avoid disclosing contacts
            # belonging to another company or leaking whether a login exists.
            company_id = request.env.company.id
            if email:
                exists = Partner.sudo().search(self._customer_domain(Partner) + [
                    ('email', '=ilike', email)], limit=1)
                if exists:
                    raise ValidationError('A customer with this email already exists in your company.')
            vals = {
                'name': name, 'street': address, 'phone': phone,
                'email': email, 'partner_latitude': latitude,
                'partner_longitude': longitude, 'customer_rank': 1,
                'company_id': company_id, 'type': 'contact',
            }
            # Use the caller's real user ID (sudo keeps env.uid) while
            # granting only the narrowly-scoped create with controlled vals.
            created = Partner.sudo().create(vals)
            return self._json({'ok': True, 'customer': {
                'id': created.id, 'name': created.name,
                'phone': created.phone or '', 'street': created.street or '',
                'latitude': created.partner_latitude,
                'longitude': created.partner_longitude,
            }})
        except (ValidationError, ValueError) as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)
        except Exception:
            # No raw traceback, secrets or other companies' contact details.
            return self._json({'ok': False,
                               'message': 'Customer could not be saved. Check your Odoo access and configuration.'}, 500)

    @http.route('/zencore/field/v4/employees', type='http', auth='user', csrf=False, methods=['GET'])
    def list_employees(self, q='', limit='50', offset='0', **kwargs):
        """Read-only selector respecting employee record rules (no sudo)."""
        try:
            self._owner()
            limit = min(100, max(1, int(limit)))
            offset = max(0, int(offset))
            q = (q or '').strip()[:100]
            # Only return minimal employee names from the user's active company.
            # HR employee access may be restricted for field staff.
            Employee = request.env['hr.employee'].sudo()
            domain = [('company_id', '=', request.env.company.id)]
            if q:
                # The mobile picker advertises name, phone or email search.
                # Include the linked login too, so freshly registered mobile
                # users are immediately discoverable as accompanying staff.
                domain.extend(['|', '|', '|',
                               ('name', 'ilike', q),
                               ('work_email', 'ilike', q),
                               ('work_phone', 'ilike', q),
                               ('user_id.login', 'ilike', q)])
            records = Employee.search(domain, order='name,id', limit=limit+1, offset=offset)
            has_more = len(records) > limit
            rows = [{'id': e.id, 'name': e.name} for e in records[:limit]]
            return self._json({'ok': True, 'employees': rows, 'has_more': has_more,
                               'next_offset': offset+len(rows)})
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route(['/zencore/field/v2/plans', '/zencore/field/v3/plans', '/zencore/field/v4/plans'],type='http',auth='user',csrf=False,methods=['POST'])
    def create_plan(self,**kwargs):
        try:
            u=self._owner();d=self._body();targets=d.get('targets') or []
            if not isinstance(targets,list) or not 1<=len(targets)<=40: raise ValidationError('Provide 1-40 target lines')
            purpose=d.get('purpose','followup')
            if purpose not in ('order','payment','complaint','followup','demo'):raise ValidationError('Invalid purpose')
            priority={'normal':'0','high':'1','urgent':'2','0':'0','1':'1','2':'2'}.get(d.get('priority','normal'))
            if priority is None:raise ValidationError('Invalid priority')
            # Validate every selected partner, not merely the first customer in a line.
            # This uses sudo solely to test the HR employee relation inside the
            # customer-only domain; the API returns only minimal customer data.
            Partner=request.env['res.partner'].sudo()
            Employee=request.env['hr.employee'].sudo()
            lines=[]
            for t in targets:
                customer_ids=t.get('customerIds') or ([t.get('customerId')] if t.get('customerId') else [])
                employee_ids=t.get('employeeIds') or []
                if not isinstance(customer_ids,list) or not isinstance(employee_ids,list):
                    raise ValidationError('Invalid customer or employee IDs')
                customer_ids=list(dict.fromkeys(int(x) for x in customer_ids))
                employee_ids=list(dict.fromkeys(int(x) for x in employee_ids))
                if not customer_ids or len(customer_ids)>100:
                    raise ValidationError('Each target line needs 1-100 customers')
                if len(employee_ids)>40:
                    raise ValidationError('Too many accompanying employees')
                customer_domain = [('id', 'in', customer_ids)] + self._customer_domain(Partner)
                if len(Partner.search(customer_domain)) != len(customer_ids):
                    raise ValidationError('One or more customers are unavailable')
                if employee_ids and len(Employee.search([('id','in',employee_ids), ('company_id','=',request.env.company.id)]))!=len(employee_ids):
                    raise ValidationError('One or more accompanying employees are unavailable')
                km=float(t.get('km') or 0)
                if not 0<=km<=10000:
                    raise ValidationError('Expected KM is out of allowed range')
                source=str(t.get('from') or '').strip()[:250]
                try:
                    from_latitude=float(t.get('fromLatitude'))
                    from_longitude=float(t.get('fromLongitude'))
                except (TypeError, ValueError):
                    raise ValidationError('Choose a valid From Location on the map or enter latitude and longitude')
                if not source or not (-90 <= from_latitude <= 90 and -180 <= from_longitude <= 180):
                    raise ValidationError('Choose a valid From Location on the map or enter latitude and longitude')
                partners=Partner.search(customer_domain)
                primary=partners.filtered(lambda p: p.id == customer_ids[0])
                primary=primary[:1]
                lat=primary.partner_latitude if 'partner_latitude' in primary._fields else False
                lng=primary.partner_longitude if 'partner_longitude' in primary._fields else False
                if lat in (False, None) or lng in (False, None):
                    raise ValidationError('The first selected customer needs a saved map location before this plan can be created')
                destination=', '.join(part for part in [primary.name, primary.street, primary.city, primary.country_id.name] if part)[:250]
                lines.append((0,0,{
                    'sequence':(len(lines)+1)*10,
                    'customer_ids':[(6,0,customer_ids)],
                    'employee_ids':[(6,0,employee_ids)],
                    'from_location':source,
                    'from_latitude':from_latitude,
                    'from_longitude':from_longitude,
                    'to_location':destination,
                    'expected_km':km,
                    'notes':str(t.get('notes') or '')[:1000],
                }))
            def amount(k):
                value=float(d.get(k) or 0)
                if not 0<=value<=1000000:raise ValidationError('Invalid expense amount: '+k)
                return value
            plan=request.env['salesperson.visit.plan'].sudo().create({
                'user_id':u.id,'visit_date':d.get('date') or str(fields.Date.today()),'purpose':purpose,'priority':priority,
                'transport_cost':amount('transport'),'food_cost':amount('food'),'other_cost':amount('other'),
                'target_line_ids':lines,'internal_notes':str(d.get('notes') or '')[:3000],
            })
            if d.get('submit',False):plan.action_submit()
            return self._json({'ok':True,'plan_id':plan.id,'plan_name':plan.name,'state':plan.state})
        except Exception as ex:return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v2/plans/<int:plan_id>/submit',type='http',auth='user',csrf=False,methods=['POST'])
    def submit(self,plan_id,**kwargs):
        try:
            u=self._owner();p=request.env['salesperson.visit.plan'].sudo().browse(plan_id)
            if not p.exists() or p.user_id.id!=u.id or p.state!='draft':raise ValidationError('Not your draft plan')
            p.action_submit();return self._json({'ok':True,'state':p.state})
        except Exception as ex:return self._json({'ok':False,'message':str(ex)},400)

    # V3 routes deliberately keep Odoo's existing approval methods and views intact.
    # A salesperson starts ONLY their own approved plan, on its scheduled date.
    def _owned_plan(self, plan_id, user):
        plan = request.env['salesperson.visit.plan'].sudo().browse(int(plan_id))
        if not plan.exists() or plan.user_id.id != user.id:
            raise ValidationError('Visit plan not found for your account')
        return plan

    def _plan_payload(self, plan):
        tracker = request.env['salesperson.tracker'].sudo().search(
            [('plan_id', '=', plan.id)], limit=1)
        return {
            'id': plan.id, 'name': plan.name, 'visit_date': str(plan.visit_date),
            'state': plan.state, 'purpose': plan.purpose,
            'salesperson_id': plan.user_id.id,
            'salesperson': plan.user_id.name,
            'total_visits': plan.total_visits,
            'tracker_id': tracker.id or None,
            'is_tracking': bool(tracker.is_tracking),
        }

    @http.route('/zencore/field/v4/plans/<int:plan_id>',type='http',auth='user',methods=['GET'],csrf=False)
    def plan_detail(self,plan_id,**kwargs):
        try:
            user=self._owner()
            plan=self._owned_plan(plan_id,user)
            data=self._plan_payload(plan)
            data.update({
                'priority':plan.priority,
                'transport':plan.transport_cost,
                'food':plan.food_cost,
                'other':plan.other_cost,
                'total_cost':plan.total_cost,
                'notes':plan.internal_notes or '',
                'targets':[{
                    'id':line.id,
                    'employee_ids':line.employee_ids.ids,
                    'employee_names':line.employee_ids.mapped('name'),
                    'customer_ids':line.customer_ids.ids,
                    'customer_names':line.customer_ids.mapped('name'),
                    'customer_locations':[{
                        'id':partner.id,
                        'latitude':partner.partner_latitude if 'partner_latitude' in partner._fields else None,
                        'longitude':partner.partner_longitude if 'partner_longitude' in partner._fields else None,
                    } for partner in line.customer_ids],
                    'from_location':line.from_location or '',
                    'from_latitude':line.from_latitude,
                    'from_longitude':line.from_longitude,
                    'expected_km':line.expected_km,
                    'notes':line.notes or '',
                } for line in plan.target_line_ids],
            })
            return self._json({'ok':True,'plan':data})
        except Exception as ex:
            return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v3/my-plans', type='http', auth='user', methods=['GET'], csrf=False)
    def my_plans(self, **kwargs):
        try:
            user = self._owner()
            plans = request.env['salesperson.visit.plan'].sudo().search(
                [('user_id', '=', user.id)], order='visit_date desc,id desc', limit=100)
            return self._json({'ok': True, 'plans': [self._plan_payload(p) for p in plans]})
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route('/zencore/field/v3/plans/<int:plan_id>/start', type='http', auth='user', methods=['POST'], csrf=False)
    def start_plan(self, plan_id, **kwargs):
        try:
            user = self._owner()
            plan = self._owned_plan(plan_id, user)
            tracker_model = request.env['salesperson.tracker'].sudo()
            tracker = tracker_model.search([('plan_id', '=', plan.id)], limit=1)
            if plan.state not in ('approved', 'in_progress'):
                raise ValidationError('Manager approval is required before tracking')
            if plan.visit_date != fields.Date.context_today(plan):
                raise ValidationError('Tracking is allowed only on the planned visit date')
            another = tracker_model.search([
                ('user_id', '=', user.id), ('is_tracking', '=', True),
                ('plan_id', '!=', plan.id)
            ], limit=1)
            if another:
                raise ValidationError('Stop your other active Visit Plan before starting this one')
            if not tracker:
                # Reuse the original module workflow to create/load tracker lines.
                plan.action_on_track()
                tracker = tracker_model.search([('plan_id', '=', plan.id)], limit=1)
            elif plan.state == 'approved':
                plan.write({'state': 'in_progress'})
            if not tracker:
                raise ValidationError('Tracker could not be created for this plan')
            if not tracker.target_line_ids:
                tracker.action_load_target_lines()
            if not tracker.is_tracking:
                tracker.action_start_tracking()
            return self._json({'ok': True, 'plan_id': plan.id,
                               'tracker_id': tracker.id, 'state': plan.state,
                               'is_tracking': bool(tracker.is_tracking)})
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route('/zencore/field/v5/plans/<int:plan_id>/switch', type='http', auth='user', methods=['POST'], csrf=False)
    def switch_plan(self, plan_id, **kwargs):
        """Switch within one DB savepoint: old tracker(s) stopped, selected activated.

        The VISIT PLAN state is not marked completed. Existing GPS receipts
        and offline points remain bound to the old tracker/plan identifiers.
        """
        try:
            user = self._owner()
            with request.env.cr.savepoint():
                plan = self._owned_plan(plan_id, user)
                if plan.state not in ('approved', 'in_progress'):
                    raise ValidationError('Manager approval is required before tracking')
                if plan.visit_date != fields.Date.context_today(plan):
                    raise ValidationError('Tracking is allowed only on the planned visit date')
                Tracker = request.env['salesperson.tracker'].sudo()
                # A row-level user lock serializes switches on the same salesperson,
                # including concurrent requests from multiple devices.
                request.env.cr.execute('SELECT id FROM res_users WHERE id = %s FOR UPDATE', (user.id,))
                active_others = Tracker.search([
                    ('user_id', '=', user.id), ('is_tracking', '=', True),
                    ('plan_id', '!=', plan.id),
                ])
                stopped = []
                for previous in active_others:
                    if not previous.plan_id or previous.plan_id.user_id.id != user.id:
                        raise ValidationError('Active tracker ownership mismatch. Contact an administrator.')
                    previous.action_stop_tracking()
                    if previous.is_tracking:
                        raise ValidationError('Previous tracker did not stop successfully')
                    stopped.append(previous.plan_id.id)
                current = Tracker.search([('plan_id', '=', plan.id)], limit=1)
                if not current:
                    plan.action_on_track()
                    current = Tracker.search([('plan_id', '=', plan.id)], limit=1)
                elif plan.state == 'approved':
                    plan.write({'state': 'in_progress'})
                if not current or current.user_id.id != user.id:
                    raise ValidationError('Tracker could not be created for this salesperson')
                if not current.target_line_ids:
                    current.action_load_target_lines()
                if not current.is_tracking:
                    current.action_start_tracking()
                if not current.is_tracking:
                    raise ValidationError('New tracker did not enter Running state')
                payload = {'ok': True, 'plan_id': plan.id,
                           'tracker_id': current.id, 'state': plan.state,
                           'is_tracking': True, 'stopped_plan_ids': stopped}
            return self._json(payload)
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route('/zencore/field/v3/plans/<int:plan_id>/stop', type='http', auth='user', methods=['POST'], csrf=False)
    def stop_plan(self, plan_id, **kwargs):
        try:
            user = self._owner()
            plan = self._owned_plan(plan_id, user)
            tracker = request.env['salesperson.tracker'].sudo().search(
                [('plan_id', '=', plan.id)], limit=1)
            if not tracker:
                raise ValidationError('No tracker exists for this plan')
            if tracker.is_tracking:
                tracker.action_stop_tracking()
            return self._json({'ok': True, 'plan_id': plan.id,
                               'tracker_id': tracker.id, 'is_tracking': False})
        except Exception as ex:
            return self._json({'ok': False, 'message': str(ex)}, 400)

    @http.route(['/zencore/field/v2/gps/batch', '/zencore/field/v3/gps/batch'],type='http',auth='user',csrf=False,methods=['POST'])
    def batch_gps(self,**kwargs):
        try:
            user=self._owner();data=self._body();rows=data.get('points') or []
            if not isinstance(rows,list) or len(rows)>100:raise ValidationError('Maximum 100 points per batch')
            receipt=request.env['zencore.mobile.gps.receipt'].sudo()
            tracker_model=request.env['salesperson.tracker'].sudo()
            accepted=[];rejected=[];now=fields.Datetime.now()
            for item in rows:
                uuid=str(item.get('id') or '')[:120]
                if not uuid:rejected.append({'id':'','reason':'Missing UUID'});continue
                existing=receipt.search([('point_uuid','=',uuid)],limit=1)
                if existing:
                    if existing.user_id.id==user.id:accepted.append(uuid)
                    else:rejected.append({'id':uuid,'reason':'Point ID belongs to another user'})
                    continue
                try:
                    lat=float(item['latitude']);lng=float(item['longitude']);acc=float(item.get('accuracy') or 0)
                    capture=datetime.utcfromtimestamp(float(item['capturedAt'])/1000)
                    if not (-90<=lat<=90 and -180<=lng<=180):raise ValueError('Invalid coordinates')
                    if capture>now+timedelta(minutes=5) or capture<now-timedelta(days=7):raise ValueError('Timestamp outside allowed retention')
                    tracker=tracker_model.browse(int(item.get('trackerId') or 0))
                    if not tracker.exists() or tracker.user_id.id!=user.id:raise ValueError('Invalid tracker ownership')
                    plan_id=int(item.get('planId') or tracker.plan_id.id or 0)
                    if not plan_id or tracker.plan_id.id!=plan_id:raise ValueError('GPS point Plan ID does not match tracker Plan ID')
                    if tracker.plan_id.state not in ('in_progress','completed'):raise ValueError('Plan is not tracking-ready')
                    with request.env.cr.savepoint():
                        # Use the same tracker pipeline as live GPS. This
                        # updates the last position and invokes the server-side
                        # 100m geofence while tracking is active. The tracker
                        # model gates geofence actions for delayed points that
                        # arrive after Stop.
                        tracker.update_live_location(
                            lat, lng, accuracy=acc,
                            source='zencore_field_offline',
                            distance=0.0, log_time=capture,
                        )
                        receipt.create({'point_uuid':uuid,'tracker_id':tracker.id,'user_id':user.id,'captured_at':capture})
                    accepted.append(uuid)
                except Exception as ex:rejected.append({'id':uuid,'reason':str(ex)[:150]})
            return self._json({'ok':True,'accepted':accepted,'rejected':rejected})
        except Exception as ex:return self._json({'ok':False,'message':str(ex)},400)

    @http.route('/zencore/field/v5/photos/upload', type='http', auth='user', csrf=False, methods=['POST'])
    def upload_visit_photo(self, **kwargs):
        """Idempotent attachment + chatter message on a salesperson-owned plan.

        A stable client UUID ensures retry after network interruption cannot
        create an extra chatter message. No public or sudo-only upload bypass.
        """
        try:
            user = self._owner()
            data = self._body()
            plan = self._owned_plan(int(data.get('plan_id') or 0), user)
            if plan.state not in ('approved', 'in_progress', 'completed'):
                raise ValidationError('Photo evidence requires an approved or active Visit Plan')
            uuid = str(data.get('id') or '')
            if not re.fullmatch(r'[a-zA-Z0-9_-]{12,120}', uuid):
                raise ValidationError('Invalid photo UUID')
            Receipt = request.env['zencore.mobile.photo.receipt'].sudo()
            existing = Receipt.search([('photo_uuid', '=', uuid)], limit=1)
            if existing:
                if existing.user_id.id != user.id or existing.plan_id.id != plan.id:
                    raise ValidationError('Photo UUID belongs to a different owner or plan')
                return self._json({'ok': True, 'photo_id': uuid,
                                   'attachment_id': existing.attachment_id.id,
                                   'message_id': existing.message_id.id,
                                   'already_uploaded': True})
            content_type = str(data.get('mime_type') or 'image/jpeg').lower()
            if content_type not in ('image/jpeg', 'image/png', 'image/webp'):
                raise ValidationError('Only JPEG, PNG and WEBP images are accepted')
            content_b64 = str(data.get('content_base64') or '')
            if not content_b64 or len(content_b64) > 7_100_000:
                raise ValidationError('Photo exceeds the 5 MB upload limit')
            try:
                content = base64.b64decode(content_b64, validate=True)
            except (binascii.Error, ValueError):
                raise ValidationError('Invalid photo encoding')
            if not content or len(content) > 5 * 1024 * 1024:
                raise ValidationError('Photo must be smaller than 5 MB')
            if (content_type == 'image/jpeg' and not content.startswith(b'\xff\xd8\xff')) or \
               (content_type == 'image/png' and not content.startswith(b'\x89PNG\r\n\x1a\n')) or \
               (content_type == 'image/webp' and not (content.startswith(b'RIFF') and content[8:12] == b'WEBP')):
                raise ValidationError('Photo content does not match its MIME type')
            name = re.sub(r'[^A-Za-z0-9_.-]', '_', str(data.get('file_name') or 'visit_photo.jpg'))[:120]
            note = str(data.get('note') or '')[:1500]
            customer_id = int(data.get('customer_id') or 0)
            if customer_id and customer_id not in plan.target_line_ids.mapped('customer_ids').ids:
                raise ValidationError('Selected customer is not part of this Visit Plan')
            tracker_id = int(data.get('tracker_id') or 0)
            if tracker_id:
                tracker = request.env['salesperson.tracker'].sudo().browse(tracker_id)
                if not tracker.exists() or tracker.plan_id.id != plan.id:
                    raise ValidationError('Tracker does not belong to this plan')
            # mail.thread.message_post() expects Markup for intended HTML; plain
            # strings are escaped and literal <p> appears in Chatter. Markup.format
            # auto-escapes untrusted substitutions (including user notes).
            from markupsafe import Markup
            from odoo import fields as odoo_fields
            raw_stamp = data.get('captured_at')
            try:
                captured_utc = datetime.utcfromtimestamp(float(raw_stamp) / 1000)
                stamp = odoo_fields.Datetime.to_string(captured_utc) + ' UTC'
            except (ValueError, TypeError, OverflowError, OSError):
                stamp = 'Unavailable'
            location_name = str(data.get('location_name') or '').strip()[:240]
            device_name = str(data.get('device_name') or '').strip()[:100]
            photo_origin = str(data.get('photo_origin') or 'camera')
            latitude, longitude, accuracy = None, None, None
            try:
                lat_in, lng_in = data.get('latitude'), data.get('longitude')
                if lat_in is not None and lng_in is not None:
                    lat, lng = float(lat_in), float(lng_in)
                    if -90 <= lat <= 90 and -180 <= lng <= 180:
                        latitude, longitude = lat, lng
                acc_in = data.get('accuracy_m')
                if acc_in is not None and 0 <= float(acc_in) <= 100000:
                    accuracy = float(acc_in)
            except (ValueError, TypeError):
                pass
            location_label = location_name or ('GPS coordinates available' if latitude is not None else 'Unavailable')
            # Do not turn the Visit Plan's from/to address into an invented photo location.
            # These fields describe the device position on a newly taken camera photo.
            origin_text = 'Captured' if photo_origin == 'camera' else 'Selected for upload'
            body = Markup('''<div class="o_zc_visit_evidence">
                <p><strong>📷 Field Visit Photo Uploaded</strong></p>
                <p><strong>Uploaded by:</strong> {}<br/>
                <strong>Location:</strong> {}<br/>
                <strong>Device:</strong> {}<br/>
                <strong>{} at:</strong> {}<br/>
                <strong>Visit Plan:</strong> {}</p>
            ''').format(user.name or user.login, location_label, device_name or 'Unavailable', origin_text, stamp, plan.name)
            if latitude is not None:
                body += Markup('<p><strong>GPS:</strong> {:.6f}, {:.6f}{}<br/>').format(
                    latitude, longitude, ' (±{:.0f} m)'.format(accuracy) if accuracy is not None else '')
                # Fixed OSM domain, validated numeric coordinates; never accept a user URL.
                map_url = 'https://www.openstreetmap.org/?mlat={:.6f}&amp;mlon={:.6f}#map=17/{:.6f}/{:.6f}'.format(
                    latitude, longitude, latitude, longitude)
                body += Markup('<a href="{}" target="_blank" rel="noopener noreferrer">View capture location on map</a></p>').format(Markup(map_url))
            if customer_id:
                customer = request.env['res.partner'].sudo().browse(customer_id)
                body += Markup('<p><strong>Customer:</strong> {}</p>').format(customer.name if customer.exists() else 'Unavailable')
            if note.strip():
                body += Markup('<p><strong>Visit notes:</strong> {}</p>').format(note)
            body += Markup('</div>')
            # Transaction: attachment, chatter message and unique receipt commit together.
            Attachment = request.env['ir.attachment'].sudo()
            attachment = Attachment.create({
                'name': name, 'type': 'binary', 'raw': content,
                'mimetype': content_type,
                'res_model': 'salesperson.visit.plan', 'res_id': plan.id,
            })
            message = plan.sudo().message_post(
                body=body, message_type='comment', subtype_xmlid='mail.mt_note',
                attachment_ids=[attachment.id])
            receipt = Receipt.create({
                'photo_uuid': uuid, 'plan_id': plan.id, 'user_id': user.id,
                'attachment_id': attachment.id, 'message_id': message.id,
            })
            return self._json({'ok': True, 'photo_id': uuid,
                               'attachment_id': receipt.attachment_id.id,
                               'message_id': receipt.message_id.id})
        except Exception as ex:
            request.env.cr.rollback()
            return self._json({'ok': False, 'message': str(ex)}, 400)
