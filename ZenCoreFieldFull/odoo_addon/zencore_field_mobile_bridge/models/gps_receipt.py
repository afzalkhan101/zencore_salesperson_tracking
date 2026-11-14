from odoo import fields,models

class ZenCoreMobileGpsReceipt(models.Model):
    _name='zencore.mobile.gps.receipt'
    _description='ZenCore Field GPS Point Receipt'
    _order='id desc'
    point_uuid=fields.Char(required=True,index=True,readonly=True)
    tracker_id=fields.Many2one('salesperson.tracker',required=True,ondelete='cascade',readonly=True)
    user_id=fields.Many2one('res.users',required=True,readonly=True)
    captured_at=fields.Datetime(required=True,readonly=True)
    _sql_constraints=[('unique_point_uuid','unique(point_uuid)','GPS point UUID has already been acknowledged.')]
