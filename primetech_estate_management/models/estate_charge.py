from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EstateCharge(models.Model):
    _name = 'estate.charge'
    _description = 'Charge immobilière'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Libellé', required=True, tracking=True)
    charge_type = fields.Selection([('water', 'Eau'), ('electricity', 'Électricité'), ('security', 'Gardiennage'), ('cleaning', 'Nettoyage'), ('maintenance', 'Entretien'), ('common', 'Charges communes'), ('repair', 'Réparations'), ('other', 'Autre')], required=True, default='other')
    recurrence = fields.Selection([('fixed', 'Fixe'), ('recurring', 'Récurrente'), ('oneoff', 'Ponctuelle')], required=True, default='oneoff')
    property_id = fields.Many2one('estate.property', string='Immeuble')
    unit_id = fields.Many2one('estate.unit', string='Local', domain="[('property_id', '=', property_id)]")
    lease_id = fields.Many2one('estate.lease', string='Contrat')
    schedule_id = fields.Many2one('estate.rent.schedule', string='Échéance')
    maintenance_request_id = fields.Many2one('maintenance.request', string='Intervention de maintenance', ondelete='set null', index=True)
    supplier_id = fields.Many2one('res.partner', string='Fournisseur')
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Devise')
    amount = fields.Monetary('Montant', required=True, currency_field='currency_id')
    vendor_bill_id = fields.Many2one('account.move', string='Facture fournisseur', readonly=True, copy=False, ondelete='set null')
    amount_paid = fields.Monetary('Payé', compute='_compute_accounting_amounts', currency_field='currency_id')
    amount_residual = fields.Monetary('Reste à payer', compute='_compute_accounting_amounts', currency_field='currency_id')
    date = fields.Date('Date', default=fields.Date.context_today, required=True)
    note = fields.Text('Note')
    state = fields.Selection([
        ('draft', 'Brouillon'), ('confirmed', 'Validée'), ('billed', 'Facturée'),
        ('paid', 'Payée'), ('cancelled', 'Annulée')], default='draft', tracking=True)

    @api.depends('vendor_bill_id.amount_total', 'vendor_bill_id.amount_residual', 'vendor_bill_id.state')
    def _compute_accounting_amounts(self):
        for record in self:
            bill = record.vendor_bill_id
            record.amount_residual = bill.amount_residual if bill and bill.state == 'posted' else record.amount if record.state == 'confirmed' else 0
            record.amount_paid = (bill.amount_total - bill.amount_residual) if bill and bill.state == 'posted' else 0

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_create_vendor_bill(self):
        """Create the accounting source used by cost and profitability analysis."""
        expense_account = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id), ('account_type', '=', 'expense'),
        ], limit=1)
        if not expense_account:
            raise UserError(_('Configurez un compte de charges avant de créer la facture fournisseur.'))
        for record in self:
            if record.vendor_bill_id:
                continue
            if not record.supplier_id:
                raise UserError(_('Sélectionnez le fournisseur avant de créer la facture fournisseur.'))
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': record.supplier_id.id,
                'invoice_date': record.date,
                'invoice_line_ids': [(0, 0, {
                    'name': record.name,
                    'quantity': 1,
                    'price_unit': record.amount,
                    'account_id': expense_account.id,
                })],
                'estate_charge_id': record.id,
            })
            record.write({'vendor_bill_id': bill.id, 'state': 'billed'})
        return self[:1].action_open_vendor_bill()

    def action_open_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id, 'view_mode': 'form', 'target': 'current',
        }
