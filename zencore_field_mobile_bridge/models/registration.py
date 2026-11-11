# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

ROLE_GROUPS = {
    'salesman': 'zencore_salesperson_tracking.group_salesperson_salesman',
    'supervisor': 'zencore_salesperson_tracking.group_salesperson_supervisor',
    'manager': 'zencore_salesperson_tracking.group_salesperson_manager',
    'ceo': 'zencore_salesperson_tracking.group_salesperson_ceo',
}

class ZenCoreFieldRegistration(models.Model):
    _name = 'zencore.field.registration'
    _description = 'Mobile Field Account Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, readonly=True)
    email = fields.Char(required=True, readonly=True, index=True)
    phone = fields.Char(readonly=True)
    requested_role = fields.Selection([
        ('salesman', 'Salesperson'), ('supervisor', 'Supervisor'),
        ('manager', 'Manager'), ('ceo', 'CEO')], required=True, readonly=True)
    assigned_role = fields.Selection([
        ('salesman', 'Salesperson'), ('supervisor', 'Supervisor'),
        ('manager', 'Manager'), ('ceo', 'CEO')], default='salesman')
    reporting_to_id = fields.Many2one('res.users', string='Reports To',
        domain="[('share','=',False)]")
    state = fields.Selection([
        ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending', readonly=True, required=True)
    user_id = fields.Many2one('res.users', readonly=True)
    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    source_ip_hash = fields.Char(readonly=True, index=True)

    def _check_admin(self):
        actor = self.env.user
        if not (actor.has_group('base.group_system') or
                actor.has_group('zencore_salesperson_tracking.group_salesperson_ceo') or
                actor.has_group('zencore_salesperson_tracking.group_salesperson_manager')):
            raise AccessError(_('Only CEO/Manager can process registration requests.'))

    def write(self, vals):
        self._check_admin()
        # Status and linked user are only changed inside workflow actions.
        if {'state', 'user_id', 'reviewed_by_id', 'reviewed_at'} & set(vals) and not self.env.su:
            raise AccessError(_('Registration status is controlled by approval actions.'))
        return super().write(vals)

    def action_reject(self):
        self._check_admin()
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only pending registrations can be rejected.'))
            rec.sudo().write({'state': 'rejected', 'reviewed_by_id': self.env.uid,
                              'reviewed_at': fields.Datetime.now()})

    def action_approve(self):
        self._check_admin()
        actor = self.env.user
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only pending registrations can be approved.'))
            role = rec.assigned_role
            if role not in ROLE_GROUPS:
                raise ValidationError(_('Choose a valid role before approval.'))
            if role == 'ceo' and not actor.has_group('base.group_system'):
                raise AccessError(_('Only a System Administrator may assign CEO.'))
            if role == 'manager' and not (actor.has_group('base.group_system') or actor.has_group('zencore_salesperson_tracking.group_salesperson_ceo')):
                raise AccessError(_('Only CEO/System Administrator may assign Manager.'))
            if role in ('salesman', 'supervisor', 'manager'):
                if not rec.reporting_to_id:
                    raise ValidationError(_('Select Reports To before approval.'))
                expected = {'salesman': 'supervisor', 'supervisor': 'manager', 'manager': 'ceo'}[role]
                if rec.reporting_to_id.sudo().salesperson_role != expected:
                    raise ValidationError(_('Reports To must have role: %s') % expected)
            if self.env['res.users'].sudo().search([('login', '=ilike', rec.email)], limit=1):
                raise UserError(_('An Odoo user already exists with this login. Review the existing user instead.'))
            values = {
                'name': rec.name, 'login': rec.email, 'email': rec.email,
                'phone': rec.phone, 'salesperson_role': role,
                'zc_reports_to_id': rec.reporting_to_id.id or False,
                'group_ids': [(6, 0, [self.env.ref(ROLE_GROUPS[role]).id])],
            }
            # Internal Odoo user, not portal/public. Password is NOT accepted from
            # the mobile application; Odoo sends an email-bound signup invitation.
            values['group_ids'] = [(6, 0, [self.env.ref('base.group_user').id,
                                           self.env.ref(ROLE_GROUPS[role]).id])]
            user = self.env['res.users'].sudo().with_context(no_reset_password=True).create(values)
            rec.sudo().write({'user_id': user.id, 'state': 'approved',
                              'reviewed_by_id': self.env.uid,
                              'reviewed_at': fields.Datetime.now()})
            # If mail is misconfigured, keep the newly-created account; the
            # administrator can resend from Users with Reset Password.
            user.sudo().action_reset_password()
