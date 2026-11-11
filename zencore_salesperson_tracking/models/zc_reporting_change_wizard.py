from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ZenCoreReportingChangeWizard(models.TransientModel):
    _name = 'zc.reporting.change.wizard'
    _description = 'Change ZenCore Reporting Line'

    user_id = fields.Many2one('res.users', required=True, readonly=True)
    reports_to_id = fields.Many2one('res.users', string='Reports To')
    approval_override = fields.Selection([('default','Use Role Policy'),
                                          ('manual','Manual'), ('auto','Automatic')],
                                         required=True, default='default')

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self.reports_to_id = self.user_id.zc_reports_to_id
            self.approval_override = self.user_id.zc_approval_override

    def action_apply(self):
        self.ensure_one()
        actor = self.env.user
        if actor.salesperson_role not in ('ceo','manager') or not (
            actor.has_group('zencore_salesperson_tracking.group_salesperson_ceo') or
            actor.has_group('zencore_salesperson_tracking.group_salesperson_manager')
        ):
            raise AccessError('Only ZenCore CEO and Manager can update reporting settings.')
        target = self.user_id.sudo()
        if not target or target.id not in actor.sudo().zc_team_user_ids.ids:
            raise AccessError('Target is outside your reporting hierarchy.')
        if target.id == actor.id and actor.salesperson_role != 'ceo':
            raise AccessError('A manager cannot modify their own reporting settings.')
        if actor.salesperson_role == 'manager' and target.salesperson_role in ('ceo','manager'):
            raise AccessError('Managers cannot modify CEO or Manager reporting settings.')
        if target.company_id not in self.env.companies or actor.company_id != target.company_id:
            raise AccessError('You may manage only your own active company.')
        superior = self.reports_to_id.sudo()
        if superior and superior.id not in actor.sudo().zc_team_user_ids.ids and superior.id != actor.id:
            raise AccessError('The chosen superior is outside your reporting tree.')
        # Keep role unchanged; res.users constrains validates adjacent roles and cycles.
        target.write({'zc_reports_to_id': superior.id if superior else False,
                      'zc_approval_override': self.approval_override})
        return {'type': 'ir.actions.act_window_close'}
