from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'
    estate_schedule_id = fields.Many2one('estate.rent.schedule', string='Échéance immobilière', copy=False, index=True)
    estate_lease_id = fields.Many2one(related='estate_schedule_id.lease_id', store=True, readonly=True)
    estate_property_id = fields.Many2one(related='estate_schedule_id.property_id', store=True, readonly=True)
    estate_unit_id = fields.Many2one(related='estate_schedule_id.unit_id', store=True, readonly=True)
    estate_charge_id = fields.Many2one('estate.charge', string='Charge immobilière', copy=False, index=True)

    def _sync_estate_charge_states(self):
        for move in self.filtered('estate_charge_id'):
            if move.state != 'posted':
                continue
            move.estate_charge_id.state = 'paid' if move.payment_state == 'paid' else 'billed'

    def action_post(self):
        result = super().action_post()
        self._sync_estate_charge_states()
        return result

    def write(self, vals):
        result = super().write(vals)
        if {'state', 'payment_state', 'amount_residual'}.intersection(vals):
            self._sync_estate_charge_states()
        return result
