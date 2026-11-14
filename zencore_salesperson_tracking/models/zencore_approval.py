from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ZenCoreApprovalPolicy(models.Model):
    _name = 'zencore.approval.policy'
    _description = 'ZenCore Role Approval Policy'
    _rec_name = 'role'
    _inherit = ['mail.thread']
    _sql_constraints = [('company_role_uniq','unique(company_id,role)',
                          'Only one approval policy per role and company is allowed.')]

    company_id = fields.Many2one('res.company', required=True, default=lambda self:self.env.company)
    role = fields.Selection([('salesman','Salesperson'),('supervisor','Supervisor'),
                             ('manager','Manager'),('ceo','CEO')], required=True)
    auto_approve = fields.Boolean(string='Automatic Approval', default=False, tracking=True)
    active = fields.Boolean(default=True)


    def _check_policy_editor(self):
        actor = self.env.user
        if actor.has_group('base.group_system'):
            return
        if actor.salesperson_role not in ('ceo', 'manager') or not (
            actor.has_group('zencore_salesperson_tracking.group_salesperson_ceo') or
            actor.has_group('zencore_salesperson_tracking.group_salesperson_manager')
        ):
            raise AccessError('Only CEO and Manager may modify approval settings.')

    @api.model_create_multi
    def create(self, vals_list):
        self._check_policy_editor()
        for vals in vals_list:
            if vals.get('company_id', self.env.company.id) not in self.env.companies.ids:
                raise AccessError('You may configure only an allowed company.')
        return super().create(vals_list)

    def write(self, vals):
        self._check_policy_editor()
        if any(x.company_id.id not in self.env.companies.ids for x in self):
            raise AccessError('You may configure only an allowed company.')
        if 'company_id' in vals and vals['company_id'] not in self.env.companies.ids:
            raise AccessError('You cannot move a policy to another company.')
        return super().write(vals)

    def unlink(self):
        self._check_policy_editor()
        if any(x.company_id.id not in self.env.companies.ids for x in self):
            raise AccessError('You may configure only an allowed company.')
        return super().unlink()


class ZenCoreCompany(models.Model):
    _inherit = 'res.company'
    zc_ceo_approver_id = fields.Many2one('res.users', string='CEO Manual Approver',
        help='Designated independent approver for CEO requests when CEO Auto Approval is off.')


class ZenCoreVisitHierarchy(models.Model):
    _inherit = 'salesperson.visit.plan'

    zc_customer_search = fields.Char(compute='_compute_zc_customer_search', store=True,
                                      string='Customer Search')

    @api.depends('target_line_ids.customer_ids', 'target_line_ids.customer_ids.name')
    def _compute_zc_customer_search(self):
        for plan in self:
            plan.zc_customer_search = ', '.join(plan.target_line_ids.mapped('customer_ids.name'))

    zc_requester_role = fields.Selection(related='user_id.salesperson_role', store=True, string='Requester Role')
    zc_approver_id = fields.Many2one('res.users', string='Assigned Approver', copy=False,
                                     tracking=True, readonly=True, index=True)
    zc_approval_mode = fields.Selection([('manual','Manual'),('auto','Automatic')],
                                         readonly=True, copy=False, string='Approval Mode')
    zc_approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    zc_approved_at = fields.Datetime(string='Approved At', readonly=True, copy=False)
    zc_can_approve = fields.Boolean(compute='_compute_zc_can_approve')

    def _compute_zc_can_approve(self):
        for plan in self:
            plan.zc_can_approve = (plan.state == 'submitted' and
                plan.zc_approver_id.id == self.env.user.id)

    def _zc_effective_approval(self):
        self.ensure_one()
        user = self.user_id.sudo()
        override = user.zc_approval_override
        if override in ('auto','manual'):
            return override
        policy = self.env['zencore.approval.policy'].sudo().search([
            ('company_id','=',self.company_id.id), ('role','=',user.salesperson_role),
            ('active','=',True)], limit=1)
        return 'auto' if policy.auto_approve else 'manual'

    def _zc_direct_approver(self):
        self.ensure_one()
        user = self.user_id.sudo()
        if user.salesperson_role == 'ceo':
            superior = self.company_id.sudo().zc_ceo_approver_id
            if superior and superior.salesperson_role != 'ceo':
                raise ValidationError('CEO manual approver must also have the CEO role.')
            if superior and (not superior.active or superior.company_id != self.company_id):
                raise ValidationError('CEO manual approver must be active and belong to this company.')
            if superior and superior.id == user.id:
                raise ValidationError('CEO cannot approve their own requests.')
            return superior
        superior = user.zc_reports_to_id
        if superior:
            if not superior.active or superior.company_id != self.company_id:
                raise ValidationError('Direct approver must be active and belong to the same company.')
            if superior.salesperson_role not in user._zc_allowed_reporting_superior_roles():
                raise ValidationError('Configured direct approver is not allowed for this role.')
            return superior

        # Reports To is optional. Prefer an explicitly designated company CEO;
        # if none is configured, a single active CEO can safely receive manual
        # approvals. Ambiguous/no-CEO cases remain submitted and visible to the
        # company CEO in monitoring, without granting the registrant privileges.
        fallback = self.company_id.sudo().zc_ceo_approver_id
        if fallback and fallback.active and fallback.company_id == self.company_id and fallback.salesperson_role == 'ceo':
            return fallback
        ceos = self.env['res.users'].sudo().search([
            ('company_id', '=', self.company_id.id), ('salesperson_role', '=', 'ceo'),
            ('active', '=', True), ('share', '=', False),
        ], limit=2)
        return ceos if len(ceos) == 1 else self.env['res.users']

    def action_reassign_direct_approver(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError('Only ZenCore system administrators can repair legacy approvers.')
        for plan in self:
            if plan.state != 'submitted':
                raise ValidationError('Only Pending Approval plans can be reassigned.')
            superior = plan._zc_direct_approver()
            if not superior:
                raise ValidationError('Configure a CEO manual approver first.')
            plan.sudo().write({'zc_approver_id':superior.id,'zc_approval_mode':'manual'})
            plan.message_post(body='Pending request reassigned to the configured direct approver by administrator.')
        return True

    def action_submit(self):
        for plan in self:
            if plan.state != 'draft':
                continue
            if plan.user_id.id != self.env.user.id and not self.env.user.has_group('base.group_system'):
                raise AccessError('Only the owner can submit this Visit Plan.')
            mode = plan._zc_effective_approval()
            superior = plan._zc_direct_approver()
            # Even automatic requests from non-CEO staff need an intact reporting tree.
            plan.write({'state':'submitted', 'zc_approver_id':superior.id if superior else False,
                        'zc_approval_mode':mode, 'zc_approved_by_id':False, 'zc_approved_at':False})
            if mode == 'auto':
                plan.sudo().with_context(zc_auto_policy=True).action_approve()
                plan.message_post(body='Automatically approved by ZenCore role/user policy.')
            elif not superior:
                plan.message_post(
                    body='Submitted without a direct approver. A CEO can monitor it and assign a reporting line.'
                )
            else:
                plan.message_post(body='Submitted for approval to %s.' % superior.name)
        return True

    def action_approve(self):
        for plan in self:
            if plan.state != 'submitted':
                raise ValidationError('Only submitted plans can be approved.')
            auto = bool(self.env.context.get('zc_auto_policy'))
            if auto:
                # Never accept a client-supplied context flag as authorization.
                # Only internal code uses sudo for automatic approval; if the policy
                # has changed since submission, fail closed.
                if not self.env.su or plan._zc_effective_approval() != 'auto' or plan.zc_approval_mode != 'auto':
                    raise AccessError('Automatic approval policy is not enabled.')
            elif plan.zc_approver_id.id != self.env.user.id:
                raise AccessError('Only the directly assigned approver can approve this plan.')
            plan.write({'state':'approved', 'zc_approved_by_id':False if auto else self.env.user.id,
                        'zc_approved_at':fields.Datetime.now()})
        return True

    def action_reject(self):
        for plan in self:
            if plan.state != 'submitted' or plan.zc_approver_id.id != self.env.user.id:
                raise AccessError('Only the assigned approver can reject a submitted plan.')
            plan.write({'state':'rejected'})
        return True

    def action_on_track(self):
        for plan in self:
            if plan.state not in ('approved','in_progress'):
                raise ValidationError('Approval is required before starting tracking.')
            if plan.user_id.id != self.env.user.id and not self.env.user.has_group('base.group_system'):
                raise AccessError('You can start only your own Visit Plan.')
        return super().action_on_track()

    def write(self, vals):
        # Direct RPC/write must never bypass the approval buttons.
        if 'state' in vals:
            new_state = vals['state']
            for plan in self:
                if new_state == 'approved':
                    if plan.state != 'submitted':
                        raise ValidationError('Only submitted plans may be approved.')
                    if not self.env.su and plan.zc_approver_id.id != self.env.user.id:
                        raise AccessError('Only your direct approver may approve this plan.')
                    if not self.env.su and vals.get('zc_approved_by_id') != self.env.user.id:
                        raise ValidationError('Approval must record the approver.')
                    if not vals.get('zc_approved_at'):
                        raise ValidationError('Use the Approve button to record approval audit.')
                if new_state == 'rejected' and plan.state != 'submitted':
                    raise ValidationError('Only submitted plans can be rejected.')
                if new_state == 'rejected' and not self.env.su and plan.zc_approver_id.id != self.env.user.id:
                    raise AccessError('Only your direct approver may reject this plan.')
                if new_state == 'in_progress' and plan.state not in ('approved','in_progress'):
                    raise ValidationError('Unapproved Visit Plans cannot start tracking.')
                if new_state == 'submitted':
                    if not self.env.su and plan.user_id.id != self.env.user.id:
                        raise AccessError('Only the Visit Plan owner may submit.')
                    if vals.get('zc_approval_mode') != plan._zc_effective_approval():
                        raise ValidationError('Submit using the Submit button to apply approval policy.')
                    superior = plan._zc_direct_approver()
                    if vals.get('zc_approver_id') != (superior.id if superior else False):
                        raise ValidationError('Submit must use the configured reporting superior.')
        protected = {'zc_approver_id', 'zc_approval_mode', 'zc_approved_by_id', 'zc_approved_at'}
        if protected.intersection(vals) and 'state' not in vals and not self.env.su:
            for plan in self:
                if plan.state != 'draft':
                    raise AccessError('Approval metadata cannot be edited directly.')
        return super().write(vals)

    def action_reset_draft(self):
        if not self.env.user.has_group('base.group_system'):
            for plan in self:
                if plan.user_id.id != self.env.user.id:
                    raise AccessError('Only the owner can reset a plan.')
        result = super().action_reset_draft()
        self.write({'zc_approver_id':False, 'zc_approval_mode':False,
                    'zc_approved_by_id':False, 'zc_approved_at':False})
        return result
