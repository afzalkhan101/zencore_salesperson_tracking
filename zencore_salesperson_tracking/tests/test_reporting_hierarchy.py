from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestZenCoreReportingHierarchy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Users = cls.env['res.users'].sudo()
        cls.company = cls.env.company
        cls._sequence = 0

    @classmethod
    def _user(cls, role, reports_to=False, company=False):
        cls._sequence += 1
        company = company or cls.company
        serial = cls._sequence
        return cls.Users.with_context(no_reset_password=True).create({
            'name': 'Hierarchy %s %s' % (role, serial),
            'login': 'hierarchy.%s.%s@example.test' % (role, serial),
            'email': 'hierarchy.%s.%s@example.test' % (role, serial),
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'salesperson_role': role,
            'zc_reports_to_id': reports_to.id if reports_to else False,
        })

    def test_flexible_roles_optional_manager_and_ceo_scope(self):
        ceo = self._user('ceo')
        manager = self._user('manager', ceo)
        supervisor_to_ceo = self._user('supervisor', ceo)
        supervisor_to_manager = self._user('supervisor', manager)
        salesperson_to_ceo = self._user('salesman', ceo)
        salesperson_to_manager = self._user('salesman', manager)
        salesperson_to_supervisor = self._user('salesman', supervisor_to_manager)
        unassigned_salesperson = self._user('salesman')

        self.assertFalse(unassigned_salesperson.zc_reports_to_id)
        self.assertTrue({
            manager.id, supervisor_to_ceo.id, supervisor_to_manager.id,
            salesperson_to_ceo.id, salesperson_to_manager.id,
            salesperson_to_supervisor.id, unassigned_salesperson.id,
        }.issubset(set(ceo.zc_team_user_ids.ids)))

    def test_invalid_reporting_lines_are_rejected(self):
        ceo = self._user('ceo')
        manager = self._user('manager', ceo)
        salesperson = self._user('salesman', manager)
        other_company = self.env['res.company'].sudo().create({
            'name': 'ZenCore Hierarchy Other Company',
        })
        other_ceo = self._user('ceo', company=other_company)

        with self.assertRaises(ValidationError):
            ceo.write({'zc_reports_to_id': manager.id})
        with self.assertRaises(ValidationError):
            salesperson.write({'zc_reports_to_id': salesperson.id})
        with self.assertRaises(ValidationError):
            ceo.write({'zc_reports_to_id': salesperson.id})
        with self.assertRaises(ValidationError):
            salesperson.write({'zc_reports_to_id': other_ceo.id})
        with self.assertRaises(ValidationError):
            manager.write({'active': False})
