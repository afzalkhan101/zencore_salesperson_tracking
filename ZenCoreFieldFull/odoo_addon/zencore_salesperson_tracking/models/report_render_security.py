"""Secure QWeb report entrypoints, including direct /report/pdf/<name>/<ids> URLs.

Odoo 19 has no ``groups_id`` on ir.actions.report. These report models are
invoked by the QWeb engine before templates receive their recordsets.
"""
from odoo import api, models, _
from odoo.exceptions import AccessError
from .report_security import check_report_access, check_report_user, report_team_user_ids


def _visible_documents(env, model_name, docids, *, wizard=False):
    actor = check_report_access(env)
    docs = env[model_name].browse(docids).exists()
    if len(docs) != len(set(docids)):
        raise AccessError(_('Report records are missing or unavailable.'))
    allowed = report_team_user_ids(env)
    for doc in docs:
        if wizard:
            if doc.create_uid.id != actor.id:
                raise AccessError(_('You cannot print another user’s report wizard.'))
            if model_name == 'salesperson.customer.report.wizard':
                check_report_user(env, doc.user_id)
            elif model_name == 'salesperson.performance.report.wizard':
                check_report_user(env, doc.individual_user_id)
                for person in doc.user_ids:
                    check_report_user(env, person)
            if doc.line_ids and 'user_id' in doc.line_ids._fields:
                for line in doc.line_ids:
                    if line.user_id and line.user_id.id not in allowed:
                        raise AccessError(_('This report includes users outside your reporting team.'))
        elif doc.user_id.id not in allowed:
            raise AccessError(_('You cannot print reports outside your reporting hierarchy.'))
    return docs


class ZcVisitPlanReport(models.AbstractModel):
    _name = 'report.zencore_salesperson_tracking.report_visit_plan'
    _description = 'ZenCore Secure Visit Plan PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = _visible_documents(self.env, 'salesperson.visit.plan', docids)
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}


class ZcTrackingSummaryReport(models.AbstractModel):
    _name = 'report.zencore_salesperson_tracking.report_tracking_summary'
    _description = 'ZenCore Secure Tracking Summary PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = _visible_documents(self.env, 'salesperson.tracker', docids)
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}


class ZcCustomerDetailedReport(models.AbstractModel):
    _name = 'report.zencore_salesperson_tracking.report_customer_detailed_document'
    _table = 'zc_customer_report_render'
    _description = 'ZenCore Secure Customer Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = _visible_documents(self.env, 'salesperson.customer.report.wizard', docids, wizard=True)
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}


class ZcSalespersonPerformanceReport(models.AbstractModel):
    _name = 'report.zencore_salesperson_tracking.report_salesperson_performance_document'
    _table = 'zc_performance_report_render'
    _description = 'ZenCore Secure Performance Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = _visible_documents(self.env, 'salesperson.performance.report.wizard', docids, wizard=True)
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}
