from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EstateRentSchedule(models.Model):
    _name = 'estate.rent.schedule'
    _description = 'Échéance de loyer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_due desc'

    name = fields.Char('Référence', default='Nouveau', readonly=True, copy=False)
    lease_id = fields.Many2one('estate.lease', string='Contrat de bail', required=True, ondelete='cascade', index=True)
    tenant_id = fields.Many2one(related='lease_id.tenant_id', string='Locataire', store=True, readonly=True)
    property_id = fields.Many2one(related='lease_id.property_id', string='Immeuble', store=True, readonly=True)
    unit_id = fields.Many2one(related='lease_id.unit_id', string='Local', store=True, readonly=True)
    company_id = fields.Many2one(related='lease_id.company_id', string='Société', store=True, readonly=True)
    currency_id = fields.Many2one(related='lease_id.currency_id', string='Devise', readonly=True)
    period_start = fields.Date('Début de période', required=True)
    period_end = fields.Date('Fin de période', required=True)
    date_due = fields.Date('Date d’échéance', required=True, index=True)
    rent_amount = fields.Monetary('Loyer', currency_field='currency_id')
    charge_amount = fields.Monetary('Charges', currency_field='currency_id')
    penalty_amount = fields.Monetary('Pénalités', currency_field='currency_id')
    discount_amount = fields.Monetary('Remise', currency_field='currency_id')
    total_amount = fields.Monetary('Montant total', compute='_compute_amounts', store=True, currency_field='currency_id')
    invoice_id = fields.Many2one('account.move', string='Facture', readonly=True, copy=False)
    invoiced_amount = fields.Monetary('Montant facturé', compute='_compute_amounts', currency_field='currency_id')
    paid_amount = fields.Monetary('Montant payé', compute='_compute_amounts', currency_field='currency_id')
    balance_amount = fields.Monetary('Solde à payer', compute='_compute_amounts', store=True, currency_field='currency_id')
    late_days = fields.Integer('Jours de retard', compute='_compute_state', search='_search_late_days')
    state = fields.Selection([('upcoming', 'À venir'), ('due', 'À payer'), ('partial', 'Partiellement payé'), ('paid', 'Payé'), ('late', 'En retard'), ('cancelled', 'Annulé')], compute='_compute_state', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('estate.schedule') or 'Nouveau'
        return super().create(vals_list)

    @api.depends('rent_amount', 'charge_amount', 'penalty_amount', 'discount_amount', 'invoice_id.amount_total', 'invoice_id.amount_residual')
    def _compute_amounts(self):
        for rec in self:
            rec.total_amount = rec.rent_amount + rec.charge_amount + rec.penalty_amount - rec.discount_amount
            rec.invoiced_amount = rec.invoice_id.amount_total if rec.invoice_id else 0
            rec.balance_amount = rec.invoice_id.amount_residual if rec.invoice_id else rec.total_amount
            rec.paid_amount = (rec.invoice_id.amount_total - rec.invoice_id.amount_residual) if rec.invoice_id else 0

    @api.depends('date_due', 'balance_amount', 'total_amount')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state == 'cancelled':
                continue
            rec.late_days = max((today - rec.date_due).days, 0) if rec.date_due else 0
            if not rec.balance_amount:
                rec.state = 'paid'
            elif rec.paid_amount:
                rec.state = 'partial'
            elif rec.date_due > today:
                rec.state = 'upcoming'
            elif rec.date_due < today:
                rec.state = 'late'
            else:
                rec.state = 'due'

    @api.model
    def _search_late_days(self, operator, value):
        """Search dynamically on the due date instead of storing a value
        that changes every day.

        The standard views use ``late_days > 7`` and ``late_days > 30``;
        support the usual comparison operators as well for saved filters.
        """
        try:
            days = max(int(value or 0), 0)
        except (TypeError, ValueError):
            return [('id', '=', 0)]

        today = fields.Date.today()
        threshold = today - timedelta(days=days)
        operators = {
            '>': ('date_due', '<', threshold),
            '>=': ('date_due', '<=', threshold),
            '<': ('date_due', '>', threshold),
            '<=': ('date_due', '>=', threshold),
            '=': ('date_due', '=', threshold),
            '!=': ('date_due', '!=', threshold),
        }
        if operator not in operators:
            return [('id', '=', 0)]
        field_name, domain_operator, domain_value = operators[operator]
        return [(field_name, domain_operator, domain_value)]

    def action_create_invoice(self):
        for rec in self:
            if rec.invoice_id or rec.state == 'cancelled':
                continue
            income_account = self.env['account.account'].search([('company_ids', 'in', rec.company_id.id), ('account_type', '=', 'income')], limit=1)
            if not income_account:
                raise UserError(_('Configurez un compte de produits avant de créer une facture.'))
            period_label = _('Période du %s au %s') % (
                fields.Date.to_string(rec.period_start),
                fields.Date.to_string(rec.period_end),
            )
            lines = [(0, 0, {
                'name': _('Loyer %s - %s (%s)') % (rec.unit_id.display_name, rec.name, period_label),
                'quantity': 1,
                'price_unit': rec.rent_amount + rec.charge_amount + rec.penalty_amount - rec.discount_amount,
                'account_id': income_account.id,
            })]
            invoice = self.env['account.move'].create({'move_type': 'out_invoice', 'partner_id': rec.tenant_id.id, 'invoice_date': fields.Date.today(), 'invoice_date_due': rec.date_due, 'invoice_line_ids': lines, 'estate_schedule_id': rec.id})
            rec.invoice_id = invoice
        return True

    def _get_batch_invoices(self, states=None, with_residual=False):
        invoices = self.mapped('invoice_id').filtered(lambda invoice: invoice.move_type == 'out_invoice')
        if states:
            invoices = invoices.filtered(lambda invoice: invoice.state in states)
        if with_residual:
            invoices = invoices.filtered(lambda invoice: invoice.amount_residual > 0.01)
        return invoices

    def _open_invoices(self, invoices, title):
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        action.update({
            'name': title,
            'domain': [('id', 'in', invoices.ids)],
            'context': {'default_move_type': 'out_invoice'},
        })
        return action

    def action_create_invoices_batch(self):
        """Create one draft customer invoice for each selected eligible schedule."""
        eligible_schedules = self.filtered(lambda schedule: not schedule.invoice_id and schedule.state != 'cancelled')
        if not eligible_schedules:
            raise UserError(_('Sélectionnez au moins une échéance non annulée sans facture.'))
        eligible_schedules.action_create_invoice()
        return self._open_invoices(eligible_schedules.mapped('invoice_id'), _('Factures de loyers créées'))

    def action_confirm_invoices_batch(self):
        """Post draft invoices attached to the selected schedules."""
        invoices = self._get_batch_invoices(states={'draft'})
        if not invoices:
            raise UserError(_('Sélectionnez au moins une échéance avec une facture brouillon à confirmer.'))
        invoices.action_post()
        return self._open_invoices(invoices, _('Factures de loyers confirmées'))

    def action_register_payments_batch(self):
        """Open the standard Accounting payment wizard for selected open invoices."""
        invoices = self._get_batch_invoices(states={'posted'}, with_residual=True)
        if not invoices:
            raise UserError(_('Sélectionnez au moins une échéance avec une facture confirmée à régler.'))
        return invoices.action_register_payment()

    @api.model
    def _cron_create_due_activities(self):
        for rec in self.search([('state', 'in', ['due', 'late']), ('balance_amount', '>', 0)]):
            rec.activity_schedule('mail.mail_activity_data_todo', summary=_('Relancer le loyer'), note=_('Échéance %s en attente.') % rec.name, user_id=rec.lease_id.property_id.manager_id.id or self.env.user.id)
