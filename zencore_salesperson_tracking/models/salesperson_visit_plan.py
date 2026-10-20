from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonVisitPlan(models.Model):
    _name = "salesperson.visit.plan"
    _description = "Visit Plan"
    _order = "visit_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    user_id = fields.Many2one("res.users", string="Salesman", required=True, tracking=True)
    company_id = fields.Many2one("res.company", related="user_id.company_id", store=True)
    sale_team_id = fields.Many2one("crm.team", related="user_id.sale_team_id", store=True)

    purpose = fields.Selection([
        ("order", "New Order"),
        ("payment", "Payment Collection"),
        ("complaint", "Complaint Resolution"),
        ("followup", "Follow Up"),
        ("demo", "Product Demo"),
    ], string="Purpose", required=True, default="followup", tracking=True)

    visit_date = fields.Date(string="Visit Date", required=True, default=fields.Date.context_today, tracking=True)
    priority = fields.Selection([
        ("0", "Normal"),
        ("1", "High"),
        ("2", "Urgent"),
    ], string="Priority", default="0", tracking=True)

    # Visit Plan Lines (Target Lines)
    target_line_ids = fields.One2many(
        "salesperson.visit.plan.line",
        "plan_id",
        string="Target Lines"
    )

    total_visits = fields.Integer(string="Total Visits", compute="_compute_total_visits", store=True)
    customer_names = fields.Char(
        string="Customers", compute="_compute_customer_names",
        help="Unique planned customers across all target lines.",
    )

    @api.depends("target_line_ids", "target_line_ids.customer_ids", "target_line_ids.customer_ids.name")
    def _compute_customer_names(self):
        for plan in self:
            customers = plan.target_line_ids.mapped("customer_ids")
            names = list(dict.fromkeys(customers.mapped("display_name")))
            plan.customer_names = (
                ", ".join(names[:3]) + (" +%d more" % (len(names) - 3) if len(names) > 3 else "")
            ) if names else False


    # Expenses
    transport_cost = fields.Float(string="Transport Cost", tracking=True)
    food_cost = fields.Float(string="Food Cost", tracking=True)
    other_cost = fields.Float(string="Other Cost", tracking=True)
    total_cost = fields.Float(string="Total Cost", compute="_compute_total_cost", store=True)

    # State
    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ], string="Status", default="draft", tracking=True)

    # Notes
    manager_notes = fields.Text(string="Manager Notes")
    internal_notes = fields.Html(string="Internal Notes")

    can_start_tracking = fields.Boolean(
        string="Can Start Tracking", compute="_compute_can_start_tracking",
        help="True if the current user is the assigned salesman for this plan, or a manager.",
    )
    is_future_visit = fields.Boolean(
        string="Is Future Visit", compute="_compute_is_future_visit",
        help="True when visit_date is strictly after today. Not stored — recomputed on "
             "every read, so a plan approved for a future date automatically becomes "
             "actionable the moment that day arrives, with no cron needed.",
    )

    def _compute_can_start_tracking(self):
        for plan in self:
            plan.can_start_tracking = (
                plan.user_id.id == self.env.user.id
                or getattr(self.env.user, 'salesperson_role', '') == 'manager'
            )

    @api.depends("visit_date")
    def _compute_is_future_visit(self):
        today = fields.Date.context_today(self)
        for plan in self:
            plan.is_future_visit = bool(plan.visit_date and plan.visit_date > today)

    @api.constrains('visit_date')
    def _check_visit_date_not_past(self):
        today = fields.Date.context_today(self)
        for plan in self:
            if plan.visit_date and plan.visit_date < today:
                raise ValidationError(_(
                    "Visit Date can't be in the past. Please pick today or a future date."
                ))

    @api.depends("target_line_ids.customer_count")
    def _compute_total_visits(self):
        for plan in self:
            total = sum(line.customer_count for line in plan.target_line_ids)
            plan.total_visits = total

    @api.depends("transport_cost", "food_cost", "other_cost")
    def _compute_total_cost(self):
        for plan in self:
            plan.total_cost = plan.transport_cost + plan.food_cost + plan.other_cost

    @api.model
    def _generate_visit_plan_ref(self, visit_date=None):
        """Generate VP/YYYY-MM-DD/NNNNN without ir.sequence. Counter is per day."""
        if not visit_date:
            visit_date = fields.Date.context_today(self)
        date_str = str(visit_date)  # YYYY-MM-DD
        count = self.search_count([("visit_date", "=", visit_date)])
        return "VP/%s/%05d" % (date_str, count + 1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                visit_date = vals.get("visit_date") or fields.Date.context_today(self)
                vals["name"] = self._generate_visit_plan_ref(visit_date)
        return super().create(vals_list)

    def action_submit(self):
        self.filtered(lambda p: p.state == "draft").write({"state": "submitted"})

    def action_approve(self):
        self.filtered(lambda p: p.state == "submitted").write({"state": "approved"})

    def action_reject(self):
        self.filtered(lambda p: p.state == "submitted").write({"state": "rejected"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_start_tracking(self):
        """Deprecated — kept only in case anything external still calls it by
        name. The 'Start Tracking' header button was replaced by the 'On
        Track' smart button (see action_on_track), which additionally
        avoids creating a duplicate tracker and actually loads target lines."""
        return self.action_on_track()

    def action_on_track(self):
        """Smart-button entry point: approved plan → live tracker.

        - Reuses an existing tracker for this plan if one is already there
          (idempotent — clicking twice, or re-opening the plan later,
          doesn't spawn duplicates).
        - Explicitly loads target lines onto the new tracker — the previous
          'Start Tracking' flow created the tracker via direct .create()
          and skipped this, which is why Live Tracking records showed no
          Tracking Lines.
        - Switches the plan to 'in_progress' and hands control straight to
          the tracker's own form view (which has its own Live Page / Map
          buttons + statusbar) rather than the raw /live URL.
        """
        self.ensure_one()
        tracker = self.env["salesperson.tracker"].search([("plan_id", "=", self.id)], limit=1)
        if not tracker:
            tracker = self.env["salesperson.tracker"].create({
                "user_id": self.user_id.id,
                "sales_person": self.user_id.name,
                "plan_id": self.id,
                "visit_date": self.visit_date,
                "purpose": self.purpose,
                "priority": self.priority,
                "transport_cost": self.transport_cost,
                "food_cost": self.food_cost,
                "other_cost": self.other_cost,
            })
        if not tracker.target_line_ids:
            tracker.action_load_target_lines()

        self.state = "in_progress"
        return {
            "type": "ir.actions.act_window",
            "res_model": "salesperson.tracker",
            "res_id": tracker.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def action_auto_complete_past_plans(self):
        """Scheduled action (see data/location_backup_cron.xml): once a
        plan's visit_date is in the past, it can no longer meaningfully be
        acted on, so mark it completed — regardless of which state it was
        stuck in (draft, submitted, approved, in_progress). 'rejected' is
        deliberately excluded: a rejected plan was an explicit decision and
        should stay Rejected, not be silently overwritten to Completed.

        The state field has tracking=True (via mail.thread), so this write
        automatically logs the old state -> 'completed' transition in each
        record's chatter — no extra logging code needed here.
        """
        today = fields.Date.today()
        past_plans = self.search([
            ("visit_date", "<", today),
            ("state", "in", ["draft", "submitted", "approved", "in_progress"]),
        ])
        if past_plans:
            past_plans.write({"state": "completed"})
        return True

    def action_view_tracker(self):
        self.ensure_one()
        tracker = self.env["salesperson.tracker"].search([("plan_id", "=", self.id)], limit=1)
        if tracker:
            return {
                "type": "ir.actions.act_window",
                "res_model": "salesperson.tracker",
                "res_id": tracker.id,
                "view_mode": "form",
                "target": "current",
            }
        return True

    def action_print_visit_plan(self):
        return self.env.ref("zencore_salesperson_tracking.action_report_visit_plan").report_action(self)
