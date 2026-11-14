"""Centralized report authorization for ZenCore Field."""
from odoo.exceptions import AccessError
from odoo import _

REPORT_ROLES = {
    'ceo': 'zencore_salesperson_tracking.group_salesperson_ceo',
    'manager': 'zencore_salesperson_tracking.group_salesperson_manager',
    'supervisor': 'zencore_salesperson_tracking.group_salesperson_supervisor',
}


def check_report_access(env):
    """Block salesperson and users without the matching tracking role group."""
    user = env.user
    if not (user.salesperson_role in REPORT_ROLES and user.has_group(REPORT_ROLES[user.salesperson_role])):
        raise AccessError(_('Only CEO, Manager and Supervisor may generate ZenCore Field reports.'))
    return user


def report_team_user_ids(env):
    actor = check_report_access(env)
    return set(actor.sudo().zc_team_user_ids.ids)


def check_report_user(env, user):
    if user and user.id not in report_team_user_ids(env):
        raise AccessError(_('You may report only on users in your reporting hierarchy.'))
