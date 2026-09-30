from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EstateDeposit(models.Model):
    _name = 'estate.deposit'
    _description = 'Caution locative'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Référence', default='Nouveau', readonly=True, copy=False)
    lease_id = fields.Many2one('estate.lease', string='Contrat de bail', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(related='lease_id.tenant_id', string='Locataire', store=True)
    company_id = fields.Many2one(related='lease_id.company_id', string='Société', store=True)
    currency_id = fields.Many2one(related='lease_id.currency_id', string='Devise')
    amount_required = fields.Monetary('Montant demandé', required=True, currency_field='currency_id')
    amount_paid = fields.Monetary('Montant versé', compute='_compute_amounts', store=True, currency_field='currency_id')
    payment_ids = fields.One2many('estate.deposit.payment', 'deposit_id', string='Versements')
    payment_count = fields.Integer(compute='_compute_amounts')
    amount_balance = fields.Monetary('Solde', compute='_compute_amounts', currency_field='currency_id')
    date = fields.Date('Date', default=fields.Date.context_today)
    return_date = fields.Date('Date de restitution', readonly=True, copy=False)
    payment_method = fields.Char('Mode de paiement')
    payment_reference = fields.Char('Référence')
    state = fields.Selection([('unpaid', 'Non versée'), ('partial', 'Partielle'), ('paid', 'Versée'), ('returned', 'Restituée'), ('partially_withheld', 'Retenue partiellement'), ('withheld', 'Retenue totalement')], compute='_compute_state', store=True, default='unpaid', tracking=True)
    history_note = fields.Text('Historique / observations')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('estate.deposit') or 'Nouveau'
        return super().create(vals_list)

    @api.depends('amount_required', 'payment_ids.amount', 'payment_ids.state')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_paid = sum(rec.payment_ids.filtered(lambda payment: payment.state == 'confirmed').mapped('amount'))
            rec.amount_balance = max(rec.amount_required - rec.amount_paid, 0)
            rec.payment_count = len(rec.payment_ids.filtered(lambda payment: payment.state == 'confirmed'))

    @api.depends('amount_required', 'amount_paid', 'return_date')
    def _compute_state(self):
        for rec in self:
            rec.state = 'returned' if rec.return_date else 'paid' if rec.amount_paid >= rec.amount_required else 'partial' if rec.amount_paid else 'unpaid'

    def action_return(self):
        self.write({'return_date': fields.Date.context_today(self)})

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'Versements de caution',
            'res_model': 'estate.deposit.payment', 'view_mode': 'list,form',
            'domain': [('deposit_id', '=', self.id)],
            'context': {'default_deposit_id': self.id},
        }


class EstateDepositPayment(models.Model):
    _name = 'estate.deposit.payment'
    _description = 'Versement de caution'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    deposit_id = fields.Many2one('estate.deposit', required=True, ondelete='cascade', index=True)
    tenant_id = fields.Many2one(related='deposit_id.tenant_id', store=True, readonly=True)
    company_id = fields.Many2one(related='deposit_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='deposit_id.currency_id', readonly=True)
    date = fields.Date('Date de versement', required=True, default=fields.Date.context_today)
    amount = fields.Monetary('Montant', required=True, currency_field='currency_id')
    payment_method = fields.Char('Mode de paiement', required=True)
    reference = fields.Char('Référence de paiement')
    note = fields.Text('Observation')
    state = fields.Selection([('draft', 'Brouillon'), ('confirmed', 'Confirmé'), ('cancelled', 'Annulé')], default='draft', required=True, tracking=True)

    def action_confirm(self):
        for payment in self:
            if payment.amount <= 0:
                raise UserError(_('Le montant du versement doit être supérieur à zéro.'))
            if payment.amount > payment.deposit_id.amount_balance and payment.deposit_id.amount_balance:
                raise UserError(_('Le versement ne peut pas être supérieur au solde de la caution.'))
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
