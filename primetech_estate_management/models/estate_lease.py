from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class EstateLease(models.Model):
    _name = 'estate.lease'
    _description = 'Contrat de bail'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char('Numéro', default='Nouveau', readonly=True, copy=False, index=True)
    tenant_id = fields.Many2one('res.partner', string='Locataire', required=True, tracking=True, domain=[('is_estate_tenant', '=', True)])
    property_id = fields.Many2one('estate.property', string='Immeuble', required=True, tracking=True)
    unit_id = fields.Many2one('estate.unit', string='Local', required=True, tracking=True, domain="[('property_id', '=', property_id)]")
    company_id = fields.Many2one(related='property_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    date_signature = fields.Date('Date de signature', default=fields.Date.context_today)
    date_start = fields.Date('Date de début', required=True, tracking=True)
    date_end = fields.Date('Date de fin', required=True, tracking=True)
    notice_date = fields.Date('Date de préavis')
    renewal_date = fields.Date('Date de renouvellement prévue')
    termination_reason = fields.Text('Motif de résiliation')
    duration_months = fields.Integer('Durée (mois)', compute='_compute_duration')
    remaining_days = fields.Integer('Jours restants', compute='_compute_duration')
    rent_amount = fields.Monetary('Loyer', required=True, currency_field='currency_id', tracking=True)
    charge_amount = fields.Monetary('Charges', currency_field='currency_id')
    deposit_amount = fields.Monetary('Caution', currency_field='currency_id')
    advance_amount = fields.Monetary('Avance', currency_field='currency_id')
    due_day = fields.Integer('Jour d’échéance', default=5, required=True)
    frequency = fields.Selection([('monthly', 'Mensuelle'), ('quarterly', 'Trimestrielle'), ('semiannual', 'Semestrielle'), ('annual', 'Annuelle')], default='monthly', required=True)
    special_terms = fields.Html('Conditions particulières')
    note = fields.Text('Notes')
    signed_document = fields.Binary('Contrat signé', attachment=True)
    signed_document_filename = fields.Char('Nom du fichier signé')
    state = fields.Selection([('draft', 'Brouillon'), ('submitted', 'À valider'), ('active', 'Actif'), ('expired', 'Expiré'), ('renewed', 'Renouvelé'), ('terminated', 'Résilié'), ('closed', 'Clôturé')], default='draft', tracking=True, required=True)
    schedule_ids = fields.One2many('estate.rent.schedule', 'lease_id', string='Échéances')
    schedule_count = fields.Integer('Nombre d’échéances', compute='_compute_counts')
    unpaid_amount = fields.Monetary('Impayés', compute='_compute_counts', currency_field='currency_id')
    deposit_id = fields.Many2one('estate.deposit', string='Caution', readonly=True, copy=False)

    _sql_constraints = [('due_day_check', 'CHECK(due_day BETWEEN 1 AND 31)', 'Le jour d’échéance doit être compris entre 1 et 31.')]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('estate.lease') or 'Nouveau'
        return super().create(vals_list)

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id:
            self.property_id = self.unit_id.property_id
            self.rent_amount = self.unit_id.indicative_rent
            self.charge_amount = self.unit_id.indicative_charge
            self.deposit_amount = self.unit_id.deposit_required

    @api.constrains('date_start', 'date_end', 'unit_id', 'state')
    def _check_dates_and_overlap(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError(_('La date de fin doit être postérieure à la date de début.'))
            if rec.unit_id and rec.date_start and rec.date_end and rec.state not in ('terminated', 'closed'):
                overlap = self.search_count([('id', '!=', rec.id), ('unit_id', '=', rec.unit_id.id), ('state', 'in', ['submitted', 'active', 'expired', 'renewed']), ('date_start', '<=', rec.date_end), ('date_end', '>=', rec.date_start)])
                if overlap:
                    raise ValidationError(_('Ce local possède déjà un bail incompatible sur cette période.'))

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            rec.duration_months = (rec.date_end.year - rec.date_start.year) * 12 + rec.date_end.month - rec.date_start.month + 1 if rec.date_start and rec.date_end else 0
            rec.remaining_days = max((rec.date_end - fields.Date.today()).days, 0) if rec.date_end else 0

    @api.depends('schedule_ids.balance_amount')
    def _compute_counts(self):
        for rec in self:
            rec.schedule_count = len(rec.schedule_ids)
            rec.unpaid_amount = sum(rec.schedule_ids.mapped('balance_amount'))

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_activate(self):
        for rec in self:
            if rec.state not in ('draft', 'submitted'):
                raise UserError(_('Seul un bail brouillon ou à valider peut être activé.'))
            rec._check_dates_and_overlap()
            rec.tenant_id.is_estate_tenant = True
            rec.write({'state': 'active'})
            rec.unit_id.write({'state': 'occupied'})
            rec._generate_schedule()
            if rec.deposit_amount and not rec.deposit_id:
                rec.deposit_id = self.env['estate.deposit'].create({'lease_id': rec.id, 'amount_required': rec.deposit_amount}).id

    def action_terminate(self):
        self.write({'state': 'terminated'})
        self._release_units()

    def action_close(self):
        self.write({'state': 'closed'})
        self._release_units()

    def action_renew(self):
        self.ensure_one()
        self.state = 'renewed'
        return {
            'type': 'ir.actions.act_window', 'res_model': 'estate.lease', 'view_mode': 'form', 'target': 'current',
            'context': {'default_tenant_id': self.tenant_id.id, 'default_property_id': self.property_id.id, 'default_unit_id': self.unit_id.id, 'default_rent_amount': self.rent_amount, 'default_charge_amount': self.charge_amount, 'default_deposit_amount': self.deposit_amount, 'default_frequency': self.frequency, 'default_date_start': self.date_end + relativedelta(days=1)},
        }

    def _release_units(self):
        for rec in self:
            active = self.search_count([('id', '!=', rec.id), ('unit_id', '=', rec.unit_id.id), ('state', '=', 'active')])
            if not active:
                rec.unit_id.state = 'available'

    def _generate_schedule(self):
        Schedule = self.env['estate.rent.schedule']
        interval = {'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12}[self.frequency]
        for lease in self:
            if lease.schedule_ids:
                continue
            current = lease.date_start.replace(day=min(lease.due_day, 28))
            if current < lease.date_start:
                current += relativedelta(months=interval)
            while current <= lease.date_end:
                period_end = min(current + relativedelta(months=interval, days=-1), lease.date_end)
                Schedule.create({'lease_id': lease.id, 'date_due': current, 'period_start': current, 'period_end': period_end, 'rent_amount': lease.rent_amount, 'charge_amount': lease.charge_amount})
                current += relativedelta(months=interval)

    def action_view_schedules(self):
        action = self.env['ir.actions.actions']._for_xml_id('primetech_estate_management.estate_schedule_action')
        action['domain'] = [('lease_id', '=', self.id)]
        return action

    @api.model
    def _cron_update_lease_states(self):
        today = fields.Date.today()
        self.search([('state', '=', 'active'), ('date_end', '<', today)]).write({'state': 'expired'})
        self.search([('state', '=', 'expired')])._release_units()
