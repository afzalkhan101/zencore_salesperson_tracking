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
