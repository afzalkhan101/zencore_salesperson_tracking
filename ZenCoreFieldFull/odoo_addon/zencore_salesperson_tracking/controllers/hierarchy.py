from odoo import http
from odoo.http import request


class ZenCoreOrganizationChart(http.Controller):
    @http.route('/zencore/field/hierarchy', type='http', auth='user', website=False)
    def hierarchy(self, **kwargs):
        """Backward-compatible redirect from legacy tree to Odoo native menu."""
        return request.redirect('/odoo', code=302)
