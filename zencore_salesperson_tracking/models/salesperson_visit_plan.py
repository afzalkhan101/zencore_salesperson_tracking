from .report_security import check_report_access
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonVisitPlan(models.Model):
    _name = "salesperson.visit.plan"
    _description = "Visit Plan"
    _order = "visit_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    zc_in_my_team = fields.Boolean(
        string="In My Reporting Team", compute="_compute_zc_in_my_team",
        search="_search_zc_in_my_team",
        help="Current user and all users reporting beneath them in the organization hierarchy."
    )

    def _compute_zc_in_my_team(self):
        team_ids = set(self.env.user.zc_team_user_ids.ids)
        for record in self:
            record.zc_in_my_team = record.user_id.id in team_ids

    @api.model
    def _search_zc_in_my_team(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise ValueError('In My Reporting Team supports boolean equality filters only.')
        team_ids = self.env.user.zc_team_user_ids.ids
        include_team = (operator == '=' and value) or (operator == '!=' and not value)
        return [('user_id', 'in' if include_team else 'not in', team_ids)]

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
    kanban_salesperson_initials = fields.Char(
        string="Kanban Salesperson Initials", compute="_compute_kanban_route_data"
    )
    kanban_route_data = fields.Json(
        string="Kanban Customer Route", compute="_compute_kanban_route_data",
        help="Read-only customer, address, route distance, and mobile visit data for the kanban card.",
    )
    kanban_route_extra_count = fields.Integer(
        string="Additional Kanban Stops", compute="_compute_kanban_route_data"
    )

    @api.depends("target_line_ids", "target_line_ids.customer_ids", "target_line_ids.customer_ids.name")
    def _compute_customer_names(self):
        for plan in self:
            customers = plan.target_line_ids.mapped("customer_ids")
            names = list(dict.fromkeys(customers.mapped("display_name")))
            plan.customer_names = (
                ", ".join(names[:3]) + (" +%d more" % (len(names) - 3) if len(names) > 3 else "")
            ) if names else False

    @api.depends(
        "user_id.name",
        "state",
        "target_line_ids.sequence",
        "target_line_ids.expected_km",
        "target_line_ids.customer_ids",
        "target_line_ids.customer_ids.name",
        "target_line_ids.customer_ids.street",
        "target_line_ids.customer_ids.street2",
        "target_line_ids.customer_ids.city",
        "target_line_ids.customer_ids.state_id",
        "target_line_ids.customer_ids.zip",
        "target_line_ids.customer_ids.country_id",
    )
    def _compute_kanban_route_data(self):
        """Create a compact, read-only route feed for the backend kanban card.

        Mobile check-ins are matched by the exact plan tracker and customer, so
        the card reflects real submitted mobile data without writing any new
        visit records. Three stops are rendered on a card; the remainder is
        represented by a concise count to keep the kanban scannable.
        """
        plan_ids = self.ids
        latest_checkins = {}
        if plan_ids:
            checkins = self.env["salesperson.checkin"].sudo().search(
                [("tracker_id.plan_id", "in", plan_ids)],
                order="checkin_time desc, id desc",
            )
            for checkin in checkins:
                key = (checkin.tracker_id.plan_id.id, checkin.partner_id.id)
                latest_checkins.setdefault(key, checkin)

        for plan in self:
            raw_stops = []
            seen_partner_ids = set()
            for line in plan.target_line_ids.sorted(lambda route_line: (route_line.sequence, route_line.id)):
                for partner in line.customer_ids:
                    if partner.id in seen_partner_ids:
                        continue
                    seen_partner_ids.add(partner.id)
                    checkin = latest_checkins.get((plan.id, partner.id))
                    address = ", ".join(filter(None, [
                        partner.street,
                        partner.street2,
                        partner.city,
                        partner.state_id.name,
                        partner.zip,
                        partner.country_id.name,
                    ]))
                    status_label = "Pending"
                    status_class = "pending"
                    visit_time = "Not visited"
                    if checkin:
                        timestamp = checkin.checkout_time or checkin.checkin_time
                        local_timestamp = fields.Datetime.context_timestamp(plan, timestamp) if timestamp else False
                        time_label = local_timestamp.strftime("%I:%M %p").lstrip("0") if local_timestamp else ""
                        if checkin.state == "checked_out":
                            status_label = "Completed"
                            status_class = "completed"
                            visit_time = "%s · Checked out" % time_label if time_label else "Completed"
                        else:
                            status_label = "Checked in"
                            status_class = "checked_in"
                            visit_time = "%s · At customer" % time_label if time_label else "Checked in"
                    raw_stops.append({
                        "name": partner.display_name or partner.name or "Customer",
                        "address": address or "Address not available",
                        "distance": ("%.2f km" % line.expected_km) if line.expected_km else "Distance unavailable",
                        "status_label": status_label,
                        "status_class": status_class,
                        "visit_time": visit_time,
                    })

            display_name = plan.user_id.name or "?"
            initials = "".join(piece[:1] for piece in display_name.split()[:2]).upper() or "?"
            plan.kanban_salesperson_initials = initials
            plan.kanban_route_data = raw_stops[:3]
            plan.kanban_route_extra_count = max(len(raw_stops) - 3, 0)


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
        """Do not silently complete pending/manual approval requests.

        Legacy code completed Draft, Submitted and Approved plans when their date
        passed; that bypassed the new hierarchy's requirement that unapproved
        plans remain pending. A historical *In Progress* plan may become
        completed only when all of its planned customers have a checked-out
        visit; merely stopping tracking or passing the visit date is not
        completion.
        """
        today = fields.Date.today()
        past = self.search([
            ('visit_date', '<', today),
            ('state', '=', 'in_progress'),
        ])
        Tracker = self.env['salesperson.tracker'].sudo()
        for plan in past:
            trackers = Tracker.search([('plan_id', '=', plan.id)])
            has_live_tracker = any(trackers.mapped('is_tracking'))
            has_completed_route = any(
                tracker._all_planned_visits_completed() for tracker in trackers
            )
            if not has_live_tracker and has_completed_route:
                plan.write({'state':'completed'})
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
        check_report_access(self.env)
        return self.env.ref("zencore_salesperson_tracking.action_report_visit_plan").report_action(self)
