from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonTrackerExpense(models.Model):
    """An auditable actual cost entered while a visit plan is being tracked."""

    _name = "salesperson.tracker.expense"
    _description = "Salesperson Actual Expense"
    _order = "expense_date desc, id desc"

    tracker_id = fields.Many2one(
        "salesperson.tracker", required=True, ondelete="cascade", index=True
    )
    plan_line_id = fields.Many2one(
        "salesperson.visit.plan.line", string="Target Line", ondelete="set null", index=True,
        help="Customer route this expense belongs to. Historical plan-level expenses remain valid.",
    )
    customer_id = fields.Many2one(
        "res.partner", string="Customer", ondelete="set null", index=True,
        help="Customer for whom this actual cost was incurred.",
    )
    plan_id = fields.Many2one(related="tracker_id.plan_id", store=True, index=True)
    user_id = fields.Many2one(related="tracker_id.user_id", store=True, index=True)
    company_id = fields.Many2one(related="tracker_id.company_id", store=True, index=True)
    reason = fields.Selection(
        [("transport", "Transport"), ("food", "Food"), ("other", "Other")],
        required=True,
        default="other",
    )
    amount = fields.Float(required=True, digits=(16, 2))
    notes = fields.Text()
    expense_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    @api.constrains("amount")
    def _check_positive_amount(self):
        for expense in self:
            if expense.amount <= 0:
                raise ValidationError(_("Actual expense amount must be greater than zero."))

    @api.constrains("tracker_id", "plan_line_id", "customer_id")
    def _check_target_belongs_to_tracker_plan(self):
        for expense in self:
            line = expense.plan_line_id
            if line and line.plan_id != expense.tracker_id.plan_id:
                raise ValidationError(_("The selected customer route is not part of this Visit Plan."))
            if expense.customer_id and line and expense.customer_id not in line.customer_ids:
                raise ValidationError(_("The selected customer is not part of the selected customer route."))
