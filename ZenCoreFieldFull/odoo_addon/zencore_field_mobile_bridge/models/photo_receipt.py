from odoo import fields, models

class ZenCoreMobilePhotoReceipt(models.Model):
    _name = 'zencore.mobile.photo.receipt'
    _description = 'ZenCore Field Chatter Photo Upload Receipt'
    photo_uuid = fields.Char(required=True, index=True, readonly=True)
    plan_id = fields.Many2one('salesperson.visit.plan', required=True, readonly=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, readonly=True)
    attachment_id = fields.Many2one('ir.attachment', required=True, readonly=True)
    message_id = fields.Many2one('mail.message', required=True, readonly=True)
    _sql_constraints = [('unique_photo_uuid', 'unique(photo_uuid)', 'Photo UUID already uploaded.')]
