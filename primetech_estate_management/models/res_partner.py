from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_estate_tenant = fields.Boolean('Est locataire', index=True)
    whatsapp = fields.Char('WhatsApp')
    id_document_number = fields.Char('N° pièce d’identité')
    id_document_expiry = fields.Date('Expiration pièce d’identité')
    tax_number = fields.Char('N° contribuable')
    emergency_contact = fields.Char('Contact d’urgence')
    estate_lease_ids = fields.One2many('estate.lease', 'tenant_id', string='Baux')
    estate_lease_count = fields.Integer('Nombre de baux', compute='_compute_estate_counts')
    estate_unpaid_amount = fields.Monetary('Impayés immobiliers', compute='_compute_estate_counts', currency_field='currency_id')

    def _compute_estate_counts(self):
        Schedule = self.env['estate.rent.schedule']
        for partner in self:
            partner.estate_lease_count = len(partner.estate_lease_ids)
            partner.estate_unpaid_amount = sum(Schedule.search([('tenant_id', '=', partner.id), ('balance_amount', '>', 0)]).mapped('balance_amount'))

    def action_view_estate_leases(self):
        action = self.env['ir.actions.actions']._for_xml_id('primetech_estate_management.estate_lease_action')
        action['domain'] = [('tenant_id', '=', self.id)]
        return action
