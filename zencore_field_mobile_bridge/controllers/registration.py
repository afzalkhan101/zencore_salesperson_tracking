
import hashlib
import json
import logging
import re
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)
_EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
_PHONE = re.compile(r'[+0-9 ()-]{7,40}')


class ZenCorePublicAccount(http.Controller):

    @http.route('/zencore/field/v10/register', type='http', auth='public',
                csrf=False, methods=['POST'])
    def register_salesperson(self, **kwargs):
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]

        def reply(data, status=200):
            return request.make_response(json.dumps(data), headers=headers, status=status)

        # Mobile self-registration is intentionally open for this deployment.
        # Accounts are still provisioned as Salesperson users only; the
        # essential input, duplicate-account and abuse-rate checks below stay
        # in place so malformed requests cannot create arbitrary Odoo users.

        try:
            raw = request.httprequest.get_data(cache=False, as_text=False)
            if len(raw) > 4096:
                return reply({'ok': False, 'message': 'Invalid registration data.'}, 400)
            data = json.loads(raw or b'{}')
            if not isinstance(data, dict):
                return reply({'ok': False, 'message': 'Invalid registration data.'}, 400)

            db = str(data.get('database') or '').strip()
            if db != request.env.cr.dbname:
                return reply({'ok': False, 'message':
                              'Database name does not match this Odoo server.'}, 400)
            name = str(data.get('name') or '').strip()
            email = str(data.get('email') or '').strip().lower()
            phone = str(data.get('phone') or '').strip()
            password = data.get('password')
            confirm = data.get('confirm_password')
            requested_role = str(data.get('requested_role') or 'salesman')

            if (not (2 <= len(name) <= 120 and len(email) <= 254 and
                     _EMAIL.fullmatch(email) and _PHONE.fullmatch(phone)) or
                    any(ord(ch) < 32 for ch in name)):
                return reply({'ok': False, 'message':
                              'Enter a valid name, email address and phone number.'}, 400)
            # Self registration never confers management privileges.
            if requested_role != 'salesman':
                return reply({'ok': False, 'message':
                              'Self-registration is available for the Salesperson role only.'}, 403)
            if not isinstance(password, str) or not isinstance(confirm, str):
                return reply({'ok': False, 'message': 'Enter and confirm your password.'}, 400)
            if not 1 <= len(password) <= 128 or any(ord(ch) < 32 for ch in password):
                return reply({'ok': False, 'message':
                              'Password must be 1–128 characters.'}, 400)
            if password != confirm:
                return reply({'ok': False, 'message': 'Passwords do not match.'}, 400)

            Registry = request.env['zencore.field.registration'].sudo()
            Config = request.env['ir.config_parameter'].sudo()
            ip = (request.httprequest.remote_addr or 'unknown').encode('utf-8')
            salt = (Config.get_param('database.secret') or request.env.cr.dbname).encode('utf-8')
            ip_hash = hashlib.sha256(salt + ip).hexdigest()
            now = fields.Datetime.now()
            if Registry.search_count([
                ('source_ip_hash', '=', ip_hash),
                ('create_date', '>=', now - timedelta(hours=1))
            ]) >= 12:
                return reply({'ok': False, 'message':
                              'Too many new accounts from this connection. Try again later.'}, 429)


            generic = {'ok': True, 'message':
                       'If this email is available, your Salesperson account is ready. Sign in with your password.'}
            Users = request.env['res.users'].sudo()

            lock_num = int.from_bytes(hashlib.sha256(email.encode()).digest()[:8], 'big', signed=True)
            request.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', (lock_num,))
            if Users.search([('login', '=ilike', email)], limit=1):
                return reply(generic)

            # The logged-in Public User must never determine the new account's
            # elevated groups. Only internal user + field salesperson group.
            salesperson_group = request.env.ref(
                'zencore_salesperson_tracking.group_salesperson_salesman')
            internal_group = request.env.ref('base.group_user')
            company = request.env.company
            values = {
                'name': name, 'login': email, 'email': email, 'phone': phone,
                'password': password, 'active': True, 'salesperson_role': 'salesman',
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(6, 0, [internal_group.id, salesperson_group.id])],
            }
            # Odoo res.users hashes the password; no password fields are written
            # on the audit record, console or any mobile persistent store.
            with request.env.cr.savepoint():
                user = Users.with_context(no_reset_password=True).create(values)
                Registry.create({
                    'name': name, 'email': email, 'phone': phone,
                    'requested_role': 'salesman', 'assigned_role': 'salesman',
                    # Public registration intentionally does not accept a user
                    # id or reporting manager. A reporting relationship can be
                    # configured later by an authorized CEO/Manager; leaving it
                    # blank never blocks the new salesperson from signing in.
                    'reporting_to_id': False,
                    'state': 'approved', 'user_id': user.id,
                    'reviewed_at': fields.Datetime.now(),
                    'source_ip_hash': ip_hash,
                })
            return reply(generic)
        except Exception:
            # No credentials, user data, raw HTTP body or SQL details are logged.
            _logger.warning('ZenCore self-registration failed (details suppressed)')
            return reply({'ok': False, 'message':
                          'Account could not be created. Check details or contact the Odoo administrator.'}, 400)
