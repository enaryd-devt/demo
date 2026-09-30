from odoo import api, fields, models


class EstatePropertyType(models.Model):
    _name = 'estate.property.type'
    _description = 'Type d’immeuble'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)


class EstateProperty(models.Model):
    _name = 'estate.property'
    _description = 'Immeuble'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('Nom', required=True, tracking=True)
    reference = fields.Char(default='Nouveau', readonly=True, copy=False, index=True)
    property_type_id = fields.Many2one('estate.property.type', string='Type', required=True, ondelete='restrict')
    manager_id = fields.Many2one('res.users', string='Gestionnaire', default=lambda self: self.env.user)
    owner_id = fields.Many2one('res.partner', string='Propriétaire')
    street = fields.Char('Adresse')
    district = fields.Char('Quartier')
    city = fields.Char('Ville')
    country_id = fields.Many2one('res.country', string='Pays')
    description = fields.Html('Description')
    image_1920 = fields.Image('Image')
    acquisition_date = fields.Date('Date d’acquisition')
    value = fields.Monetary('Valeur du bien', currency_field='currency_id')
    annual_budget = fields.Monetary('Budget annuel', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id', string='Devise', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    state = fields.Selection([('active', 'Actif'), ('inactive', 'Inactif')], default='active', tracking=True)
    unit_ids = fields.One2many('estate.unit', 'property_id', string='Locaux')
    unit_count = fields.Integer('Nombre de locaux', compute='_compute_indicators')
    occupied_unit_count = fields.Integer('Locaux occupés', compute='_compute_indicators')
    available_unit_count = fields.Integer('Locaux disponibles', compute='_compute_indicators')
    maintenance_unit_count = fields.Integer('Locaux en maintenance', compute='_compute_indicators')
    occupancy_rate = fields.Float(compute='_compute_indicators', string='Taux d’occupation (%)')
    lease_count = fields.Integer('Nombre de baux', compute='_compute_indicators')
    tenant_count = fields.Integer('Nombre de locataires', compute='_compute_indicators')
    rent_due = fields.Monetary('Loyers dus', compute='_compute_financials')
    unpaid_amount = fields.Monetary(compute='_compute_financials', string='Impayés')
    annual_rent_potential = fields.Monetary('Potentiel annuel', compute='_compute_financials', currency_field='currency_id')
    annual_invoiced_amount = fields.Monetary('Facturé sur 12 mois', compute='_compute_financials', currency_field='currency_id')
    annual_collected_amount = fields.Monetary('Encaissé sur 12 mois', compute='_compute_financials', currency_field='currency_id')
    gross_yield = fields.Float('Rendement brut (%)', compute='_compute_financials')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', 'Nouveau') == 'Nouveau':
                vals['reference'] = self.env['ir.sequence'].next_by_code('estate.property') or 'Nouveau'
        return super().create(vals_list)

    @api.depends('unit_ids.state')
    def _compute_indicators(self):
        Lease = self.env['estate.lease']
        for rec in self:
            units = rec.unit_ids
            rec.unit_count = len(units)
            rec.occupied_unit_count = len(units.filtered(lambda u: u.state == 'occupied'))
            rec.available_unit_count = len(units.filtered(lambda u: u.state == 'available'))
            rec.maintenance_unit_count = len(units.filtered(lambda u: u.state == 'maintenance'))
            rec.occupancy_rate = rec.unit_count and (100.0 * rec.occupied_unit_count / rec.unit_count) or 0.0
            leases = Lease.search_count([('property_id', '=', rec.id)])
            rec.lease_count = leases
            rec.tenant_count = len(Lease.search([('property_id', '=', rec.id), ('state', '=', 'active')]).mapped('tenant_id'))

    def _compute_financials(self):
        Schedule = self.env['estate.rent.schedule']
        Invoice = self.env['account.move']
        today = fields.Date.today()
        date_from = today.replace(month=1, day=1)
        for rec in self:
            lines = Schedule.search([('property_id', '=', rec.id), ('state', '!=', 'cancelled')])
            rec.rent_due = sum(lines.mapped('total_amount'))
            rec.unpaid_amount = sum(lines.mapped('balance_amount'))
            current_year_lines = lines.filtered(lambda line: line.date_due and line.date_due >= date_from)
            rec.annual_rent_potential = sum(current_year_lines.mapped('total_amount'))
            invoices = Invoice.search([
                ('estate_property_id', '=', rec.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('invoice_date', '>=', date_from),
            ])
            rec.annual_invoiced_amount = sum(invoices.mapped('amount_total_signed'))
            rec.annual_collected_amount = sum(invoices.mapped('amount_total_signed')) - sum(invoices.mapped('amount_residual_signed'))
            rec.gross_yield = (100 * rec.annual_invoiced_amount / rec.value) if rec.value else 0

    def action_view_units(self):
        return self._action('primetech_estate_management.estate_unit_action', [('property_id', '=', self.id)])

    def action_view_leases(self):
        return self._action('primetech_estate_management.estate_lease_action', [('property_id', '=', self.id)])

    def action_view_unpaid(self):
        return self._action('primetech_estate_management.estate_schedule_action', [('property_id', '=', self.id), ('balance_amount', '>', 0)])

    def _action(self, xmlid, domain):
        action = self.env['ir.actions.actions']._for_xml_id(xmlid)
        action['domain'] = domain
        return action
