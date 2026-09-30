from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    estate_lease_expiry_alert_days = fields.Integer(related='company_id.estate_lease_expiry_alert_days', readonly=False)
    estate_rent_reminder_days = fields.Integer(related='company_id.estate_rent_reminder_days', readonly=False)


class ResCompany(models.Model):
    _inherit = 'res.company'
    estate_lease_expiry_alert_days = fields.Integer('Alerte expiration bail (jours)', default=30)
    estate_rent_reminder_days = fields.Integer('Relance loyer après échéance (jours)', default=3)

