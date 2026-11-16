from odoo import fields, models, api
from odoo.exceptions import AccessError, ValidationError
import logging
import time
import requests

_logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# A reporting line is deliberately independent from the security role groups.
# It grants visibility only through the existing reporting-team record rules;
# it never adds a group or backend administration privilege.
ZC_ALLOWED_REPORTING_SUPERIORS = {
    'ceo': set(),
    'manager': {'ceo'},
    'supervisor': {'ceo', 'manager'},
    'salesman': {'ceo', 'manager', 'supervisor'},
}


class ResUsers(models.Model):
    _inherit = "res.users"

    salesperson_role = fields.Selection(
        [
            ("ceo", "CEO"),
            ("manager", "Manager"),
            ("supervisor", "Supervisor"),
            ("salesman", "Salesperson"),
        ],
        string="Role",
        default="salesman",
        required=True,
        help="Manager: Full access to all tracking data\nSalesman: Own records only",
    )

    @api.model
    def zc_get_field_landing_action(self):
        """Select the app landing action using the authenticated server-side role.

        Never trust a role supplied by JavaScript. This mirrors the dashboard
        controller's permissions and does not grant additional record access.
        """
        user = self.env.user
        if user.has_group('base.group_system') or user.salesperson_role in (
            'ceo', 'manager', 'supervisor'
        ):
            return 'zencore_salesperson_tracking.action_salesperson_dashboard_client'
        return 'zencore_salesperson_tracking.action_salesperson_visit_plan_my'

    zc_reports_to_id = fields.Many2one(
        'res.users', string='Reports To', ondelete='restrict', index=True,
        domain="[('active','=',True),('share','=',False),('company_ids','in',company_id)]",
        help='Optional direct reporting manager. The allowed role is validated on the server.',
    )
    zc_approval_override = fields.Selection([
        ('default','Use Role Policy'),('manual','Manual Approval'),('auto','Auto Approve')
    ], default='default', string='Approval Override',
       help='Applies to requests submitted by this user; configured by administrators.')
    zc_direct_report_ids = fields.One2many(
        'res.users', 'zc_reports_to_id', string='Direct Reports', readonly=True)
    zc_chart_visible = fields.Boolean(
        compute='_compute_zc_chart_visible', search='_search_zc_chart_visible',
        string='Visible in Organization Chart')

    def _compute_zc_chart_visible(self):
        permitted = set(self.env.user.sudo().zc_team_user_ids.ids)
        for record in self:
            record.zc_chart_visible = record.id in permitted

    def _search_zc_chart_visible(self, operator, value):
        """Search the current user's reporting subtree in native hierarchy views.

        Odoo 19 optimizes ``('boolean_field', '=', True)`` into an
        ``in`` domain during ``hierarchy_read``.  The previous implementation
        rejected this normalized operator, raising a server-side ValueError.
        Support both original and optimized Boolean-domain operators.
        """
        if operator in ('=', '!=', '=?'):
            # Odoo Boolean values may be normalized to 0/1 during filtering.
            accepted_values = {True, False, 0, 1}
            if value not in accepted_values:
                return [('id', '=', 0)]
            if operator == '=?' and not value:
                return []  # Optional equality: false/unset removes the term.
            wants_visible = bool(value)
            if operator == '!=':
                wants_visible = not wants_visible
        elif operator in ('in', 'not in'):
            candidates = value if isinstance(value, (list, tuple, set)) else [value]
            includes_true = any(v is True or v == 1 for v in candidates)
            includes_false = any(v is False or v == 0 for v in candidates)
            if includes_true and includes_false:
                return [] if operator == 'in' else [('id', '=', 0)]
            if not includes_true and not includes_false:
                return [('id', '=', 0)] if operator == 'in' else []
            wants_visible = includes_true if operator == 'in' else includes_false
        else:
            # Return an empty domain instead of crashing a hierarchy view on
            # an unsupported operator.  Do not expand access to other users.
            return [('id', '=', 0)]

        team_ids = self.env.user.sudo().zc_team_user_ids.ids
        return [('id', 'in' if wants_visible else 'not in', team_ids)]

    def action_zc_configure_team_member(self):
        self.ensure_one()
        actor = self.env.user
        if actor.salesperson_role not in ('ceo', 'manager') or not (
            actor.has_group('zencore_salesperson_tracking.group_salesperson_ceo') or
            actor.has_group('zencore_salesperson_tracking.group_salesperson_manager')
        ):
            raise AccessError('Only ZenCore CEOs and Managers can configure the hierarchy.')
        if self.id not in actor.sudo().zc_team_user_ids.ids and self != actor:
            raise AccessError('The selected person is outside your reporting team.')
        return {'type':'ir.actions.act_window', 'name':'Edit Reporting Line',
                'res_model':'zc.reporting.change.wizard', 'view_mode':'form',
                'target':'new', 'context':dict(self.env.context, default_user_id=self.id)}

    zc_team_user_ids = fields.Many2many('res.users', compute='_compute_zc_team_user_ids',
                                         string='Visible Reporting Team')

    def _compute_zc_team_user_ids(self):
        # ``active_test=False`` intentionally retains former staff in map and
        # reporting history. It does not make them able to log in or receive
        # new assignments; it only keeps historic records visible to an
        # authorized monitor.
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        for user in self:
            # Monitoring follows the company role ladder, not whether a
            # Reports To manager happens to be configured.  Reports To remains
            # useful for organization and approvals, but must never hide a
            # lower-role field user's route from an authorized monitor.
            #
            # CEO        → everyone in the same company
            # Manager    → self + Supervisor + Salesperson
            # Supervisor → self + Salesperson
            # Salesperson→ self only
            role = user.salesperson_role or 'salesman'
            visible_ids = {user.id}
            if user.company_id:
                domain = [
                    ('company_id', '=', user.company_id.id),
                    ('share', '=', False),
                ]
                if role == 'ceo':
                    visible_ids.update(Users.search(domain).ids)
                elif role == 'manager':
                    visible_ids.update(Users.search(
                        domain + [('salesperson_role', 'in', ('supervisor', 'salesman'))]
                    ).ids)
                elif role == 'supervisor':
                    visible_ids.update(Users.search(
                        domain + [('salesperson_role', '=', 'salesman')]
                    ).ids)
            user.zc_team_user_ids = [(6, 0, list(visible_ids))]

    def _zc_allowed_reporting_superior_roles(self):
        """Return the server-authoritative allowed direct-superior roles."""
        self.ensure_one()
        return ZC_ALLOWED_REPORTING_SUPERIORS.get(self.salesperson_role, set())

    @api.constrains('zc_reports_to_id', 'salesperson_role', 'company_id', 'company_ids')
    def _check_zc_reporting_line(self):
        for user in self:
            parent = user.zc_reports_to_id
            if user.salesperson_role == 'ceo' and parent:
                raise ValidationError('A CEO cannot have a direct reporting superior.')
            if not parent:
                # Reports To is optional for every non-CEO role. An approval
                # policy may still route an unassigned plan to a company CEO.
                continue
            if parent.id == user.id:
                raise ValidationError('A user cannot report to themselves.')
            if not parent.active or parent.share:
                raise ValidationError('Reports To must be an active internal user.')
            if parent.company_id != user.company_id or user.company_id not in parent.company_ids:
                raise ValidationError('Reporting superior must belong to the same company.')
            if parent.salesperson_role not in user._zc_allowed_reporting_superior_roles():
                allowed = ', '.join(sorted(
                    dict(self._fields['salesperson_role'].selection).get(role, role)
                    for role in user._zc_allowed_reporting_superior_roles()
                ))
                raise ValidationError(
                    'This role may report only to: %s.' % (allowed or 'nobody')
                )
            seen = {user.id}
            ancestor = parent
            while ancestor:
                if ancestor.id in seen:
                    raise ValidationError('Circular reporting hierarchy is not allowed.')
                seen.add(ancestor.id)
                ancestor = ancestor.zc_reports_to_id

    @api.constrains('active')
    def _check_zc_active_reporting_manager(self):
        """Do not leave active people attached to an inactive manager."""
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        for user in self.filtered(lambda current: not current.active):
            direct_reports = Users.search([
                ('zc_reports_to_id', '=', user.id), ('active', '=', True),
            ], limit=1)
            if direct_reports:
                raise ValidationError(
                    'Reassign or clear active direct reports before archiving this reporting manager.'
                )

    salesperson_tracker_ids = fields.One2many(
        "salesperson.tracker",
        "user_id",
        string="Tracking Reports",
    )

    expo_push_token = fields.Char(
        string="Mobile Push Token",
        help="Set automatically by the ZenCore Tracker app after login. Used to "
             "silently wake the app's background GPS service when Start/Stop "
             "Tracking is pressed from ANY device (PC, laptop, or mobile browser) "
             "— not just from the phone itself.",
    )

    # ── Keep salesperson_role in sync with the REAL security groups ──────────
    # `salesperson_role` (the Manager/Salesman dropdown on the user form) is
    # what this module's own custom pages check (Dashboard, /live,
    # /moving_map). But the Odoo BACKEND views — Live Tracking kanban/list —
    # are gated by ir.rule records tied to the ACTUAL security groups
    # (group_salesperson_manager / group_salesperson_salesman). Those two
    # were never linked: setting the Role dropdown to "Manager" never
    # actually added the user to group_salesperson_manager, so the "see
    # everyone's records" ir.rule never applied to them — the backend
    # kanban/list silently stayed restricted to their own records only.
    # This keeps both in sync going forward.
    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            user._sync_salesperson_role_groups()
        return users

    def write(self, vals):
        res = super().write(vals)
        # Only re-sync when 'salesperson_role' was part of THIS write — the
        # sync itself writes only 'group_ids' (never 'salesperson_role'),
        # so this guard also naturally prevents infinite recursion without
        # needing a separate context flag.
        if 'salesperson_role' in vals:
            for user in self:
                user._sync_salesperson_role_groups()
        return res

    def _sync_salesperson_role_groups(self):
        self.ensure_one()
        keys = {'ceo':'group_salesperson_ceo', 'manager':'group_salesperson_manager',
                'supervisor':'group_salesperson_supervisor', 'salesman':'group_salesperson_salesman'}
        groups = [self.env.ref('zencore_salesperson_tracking.'+key, raise_if_not_found=False)
                  for key in keys.values()]
        if not all(groups):
            return
        chosen = keys.get(self.salesperson_role, 'group_salesperson_salesman')
        commands = [(4 if xml_id.endswith(chosen) else 3, group.id)
                    for xml_id,group in zip(keys.values(),groups)]
        self.sudo().write({'group_ids': commands})

    def _register_hook(self):
        """Runs automatically on every server start / module load — no new
        XML data file needed. This retroactively fixes any user whose
        salesperson_role was already set to "Manager" before the sync
        above existed (e.g. every database that installed an earlier
        version of this module), so a plain module upgrade is enough —
        nobody has to re-pick their Role from the dropdown to fix it.
        Idempotent and cheap: only writes users that are actually out of
        sync.
        """
        super()._register_hook()
        try:
            manager_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_manager', raise_if_not_found=False)
            salesman_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_salesman', raise_if_not_found=False)
            if not manager_group or not salesman_group:
                return
            managers_out_of_sync = self.sudo().search([
                ('salesperson_role', '=', 'manager'),
                ('group_ids', 'not in', manager_group.id),
            ])
            salesmen_out_of_sync = self.sudo().search([
                ('salesperson_role', '=', 'salesman'),
                ('group_ids', 'not in', salesman_group.id),
            ])
            for user in managers_out_of_sync | salesmen_out_of_sync:
                user._sync_salesperson_role_groups()
            # Legacy installations may have assigned the Salesman group to
            # supervisors or CEOs; repair it once after all role groups exist.
            for user in self.sudo().search([('salesperson_role','in',['supervisor','ceo'])]):
                user._sync_salesperson_role_groups()
        except Exception as e:
            _logger.warning("_register_hook: salesperson role/group self-heal failed (non-fatal): %s", e)

    def _send_push_trigger(self, action, tracker_id):
        """Silently wake the ZenCore Tracker app on this user's phone.

        No-ops (does nothing, raises nothing) if the user has no app
        installed / no push token registered — the browser's own GPS loop
        remains the fallback for those users, exactly as before.
        """
        self.ensure_one()
        if not self.expo_push_token:
            return
        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json={
                    "to": self.expo_push_token,
                    "data": {"action": action, "tracker_id": tracker_id},
                    "priority": "high",
                    # No title/body/sound → delivered as a silent data
                    # message; Android wakes the app's background task
                    # handler without showing a notification tray entry.
                    "_contentAvailable": True,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
            _logger.info(
                "_send_push_trigger: user=%s action=%s tracker=%s status=%s",
                self.name, action, tracker_id, response.status_code,
            )
        except Exception as e:
            _logger.warning(
                "_send_push_trigger: failed to notify user=%s action=%s: %s",
                self.name, action, e,
            )

    def action_open_live_tracking_page(self):
        """Open live tracking page.

        Does NOT unconditionally create a tracker — only ensures one when an
        existing tracker or an approved plan for today already justifies it.
        This mirrors the guard in controllers/main.py:live_tracking_page()
        so this method (currently unreferenced by any view, kept for API
        parity) can never reintroduce the ghost-tracker bug if wired up later.
        """
        self.ensure_one()
        today = fields.Date.today()
        existing_tracker = self.env['salesperson.tracker'].search([
            ('user_id', '=', self.id), ('visit_date', '=', today),
        ], limit=1)
        if not existing_tracker:
            has_approved_plan = self.env['salesperson.visit.plan'].search_count([
                ('user_id', '=', self.id), ('visit_date', '=', today), ('state', '=', 'approved'),
            ])
            if has_approved_plan:
                self._ensure_salesperson_tracker()
        return {
            "type": "ir.actions.client",
            "tag": "salesperson_iframe_action",
            "name": "Live Tracking",
            "params": {
                "url": "/salesperson_tracking/live?_=%d" % int(time.time()),
                "title": "Live Tracking",
            },
        }

    def _ensure_salesperson_tracker(self):
        """Ensure a tracker exists for today for this user.

        Returns an existing tracker for today or creates a new one.
        Also attempts to link a matching visit plan if one exists.
        """
        self.ensure_one()
        today = fields.Date.today()

        # order='id desc' → always return the most recently created tracker for today.
        # Without this, Postgres returns an arbitrary one (usually oldest), causing
        # GPS updates and geofence checks to go to the wrong tracker when 2 exist.
        tracker = self.env['salesperson.tracker'].search([
            ('user_id', '=', self.id),
            ('visit_date', '=', today),
        ], order='id desc', limit=1)

        if tracker:
            _logger.debug(
                "_ensure_salesperson_tracker: found existing tracker id=%s for user=%s date=%s",
                tracker.id, self.name, today,
            )
            return tracker

        # Create a new tracker for today
        tracker = self.env['salesperson.tracker'].create({
            'user_id': self.id,
            'visit_date': today,
            'state': 'planned',
        })
        _logger.info(
            "_ensure_salesperson_tracker: created new tracker id=%s for user=%s date=%s",
            tracker.id, self.name, today,
        )

        # Link a plan for today if one exists
        plan = self.env['salesperson.visit.plan'].search([
            ('user_id', '=', self.id),
            ('visit_date', '=', today),
        ], limit=1)
        if plan:
            tracker.plan_id = plan.id
            tracker.action_load_target_lines()
            _logger.info(
                "_ensure_salesperson_tracker: linked plan id=%s to tracker id=%s for user=%s",
                plan.id, tracker.id, self.name,
            )
        else:
            _logger.debug(
                "_ensure_salesperson_tracker: no plan found for user=%s date=%s",
                self.name, today,
            )

        return tracker
