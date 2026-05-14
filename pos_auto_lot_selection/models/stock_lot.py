# -*- coding: utf-8 -*-

from odoo import models


class StockLot(models.Model):
    _inherit = "stock.lot"

    def get_fefo_lots(self, product_id, location_id=False):

        lots = self.search([
            ("product_id", "=", product_id),
        ])

        result = []

        for lot in lots:
            qty = sum(lot.quant_ids.mapped("quantity"))

            if qty <= 0:
                continue

            result.append({
                "lot_name": lot.name,
                "expiration_date": lot.expiration_date or lot.use_date,
                "available_qty": qty,
            })

        # FEFO sort (expiration closest first)
        result.sort(
            key=lambda x: x["expiration_date"] or "9999-12-31"
        )

        return result