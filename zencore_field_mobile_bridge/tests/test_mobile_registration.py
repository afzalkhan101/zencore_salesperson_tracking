from odoo import SUPERUSER_ID, api
from odoo.tests.common import HttpCase


class TestZenCoreMobileRegistration(HttpCase):
    def test_public_registration_creates_only_an_unassigned_salesperson(self):
        email = 'mobile.registration.%s@example.test' % self.env.cr.dbname
        # HTTP requests have a different database cursor. Use a short-lived
        # independent cursor instead of committing the test cursor.
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['ir.config_parameter'].set_param(
                'zencore_field_mobile_bridge.registration_enabled', 'True'
            )
        try:
            response = self.url_open('/zencore/field/v10/register', json={
                'database': self.env.cr.dbname,
                'name': 'Mobile Registration Test',
                'email': email,
                'phone': '+8801700000000',
                'password': 'SecurePass123',
                'confirm_password': 'SecurePass123',
                'requested_role': 'salesman',
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])

            self.env.invalidate_all()
            user = self.env['res.users'].sudo().search([('login', '=', email)], limit=1)
            self.assertTrue(user)
            self.assertEqual(user.salesperson_role, 'salesman')
            self.assertFalse(user.zc_reports_to_id)
            self.assertTrue(user.has_group(
                'zencore_salesperson_tracking.group_salesperson_salesman'
            ))
            self.assertFalse(user.has_group(
                'zencore_salesperson_tracking.group_salesperson_supervisor'
            ))
            self.assertFalse(user.has_group(
                'zencore_salesperson_tracking.group_salesperson_manager'
            ))
            self.assertFalse(user.has_group(
                'zencore_salesperson_tracking.group_salesperson_ceo'
            ))
            self.assertFalse(user.has_group('base.group_system'))

            # Password was hashed by res.users during the public request and
            # can be used immediately; no approval/reset flow is involved.
            self.authenticate(email, 'SecurePass123')
            profile_response = self.url_open('/zencore/field/v6/profile')
            self.assertEqual(profile_response.status_code, 200)
            profile = profile_response.json()
            self.assertEqual(profile['role'], 'Salesperson')
            self.assertEqual(profile['reports_to'], '')
        finally:
            # The route's cursor commits independently, so clean its fixtures
            # explicitly and restore the default disabled registration policy.
            with self.registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['res.users'].search([('login', '=', email)]).unlink()
                env['zencore.field.registration'].search([('email', '=', email)]).unlink()
                env['ir.config_parameter'].set_param(
                    'zencore_field_mobile_bridge.registration_enabled', 'False'
                )
