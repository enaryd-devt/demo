from odoo import api, fields, models


class EstateUnitType(models.Model):
    _name = 'estate.unit.type'
    _description = 'Type de local'
    _order = 'name'
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)


class EstateUnit(models.Model):
    _name = 'estate.unit'
    _description = 'Local immobilier'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'property_id, name'

    name = fields.Char('Nom / numéro', required=True, tracking=True)
    reference = fields.Char(default='Nouveau', readonly=True, copy=False, index=True)
    property_id = fields.Many2one('estate.property', string='Immeuble', required=True, ondelete='cascade', index=True)
    unit_type_id = fields.Many2one('estate.unit.type', string='Type', required=True, ondelete='restrict')
    floor = fields.Char('Étage')
    surface = fields.Float('Superficie (m²)')
    room_count = fields.Integer('Nombre de pièces')
    indicative_rent = fields.Monetary('Loyer indicatif', currency_field='currency_id')
    indicative_charge = fields.Monetary('Charges indicatives', currency_field='currency_id')
    deposit_required = fields.Monetary('Caution demandée', currency_field='currency_id')
    currency_id = fields.Many2one(related='property_id.currency_id', readonly=True)
    company_id = fields.Many2one(related='property_id.company_id', store=True, readonly=True)
    description = fields.Html('Description')
    image_1920 = fields.Image('Image')
    state = fields.Selection([('available', 'Disponible'), ('reserved', 'Réservé'), ('occupied', 'Occupé'), ('maintenance', 'Maintenance'), ('unavailable', 'Indisponible')], default='available', required=True, tracking=True)
    tenant_id = fields.Many2one('res.partner', compute='_compute_current_lease', string='Locataire actuel')
    current_lease_id = fields.Many2one('estate.lease', compute='_compute_current_lease', string='Bail actif')
    lease_ids = fields.One2many('estate.lease', 'unit_id', string='Baux', readonly=True)
    lease_count = fields.Integer('Nombre de baux', compute='_compute_lease_count')
    unpaid_amount = fields.Monetary('Impayés', compute='_compute_financial_indicators', currency_field='currency_id')
    annual_invoiced_amount = fields.Monetary('Facturé sur 12 mois', compute='_compute_financial_indicators', currency_field='currency_id')

    _sql_constraints = [('unit_reference_company_uniq', 'unique(reference, company_id)', 'La référence du local doit être unique par société.')]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', 'Nouveau') == 'Nouveau':
                vals['reference'] = self.env['ir.sequence'].next_by_code('estate.unit') or 'Nouveau'
        return super().create(vals_list)

    @api.depends('lease_ids.state', 'lease_ids.tenant_id')
    def _compute_current_lease(self):
        Lease = self.env['estate.lease']
        for unit in self:
            lease = Lease.search([('unit_id', '=', unit.id), ('state', '=', 'active')], limit=1)
            unit.current_lease_id = lease
            unit.tenant_id = lease.tenant_id

    def _compute_lease_count(self):
        grouped = self.env['estate.lease']._read_group([('unit_id', 'in', self.ids)], ['unit_id'], ['__count'])
        counts = {unit.id: count for unit, count in grouped}
        for rec in self:
            rec.lease_count = counts.get(rec.id, 0)

    def _compute_financial_indicators(self):
        Schedule = self.env['estate.rent.schedule']
        Invoice = self.env['account.move']
        year_start = fields.Date.today().replace(month=1, day=1)
        for unit in self:
            schedules = Schedule.search([('unit_id', '=', unit.id), ('state', '!=', 'cancelled')])
            unit.unpaid_amount = sum(schedules.mapped('balance_amount'))
            invoices = Invoice.search([('estate_unit_id', '=', unit.id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date', '>=', year_start)])
            unit.annual_invoiced_amount = sum(invoices.mapped('amount_total_signed'))

    def action_view_leases(self):
        action = self.env['ir.actions.actions']._for_xml_id('primetech_estate_management.estate_lease_action')
        action['domain'] = [('unit_id', '=', self.id)]
        return action
