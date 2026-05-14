# -*- coding: utf-8 -*-

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _process_order(self, order, *args, **kwargs):
        """
        Odoo 18 safe override (signature flexible)
        """

        res = super()._process_order(order, *args, **kwargs)

        pos_order = self.browse(res) if isinstance(res, int) else res

        for line in pos_order.lines:
            if line.pack_lot_ids:
                self._check_lots(line)

        return res

    # ---------------------------------------------------------
    # JUST VALIDATION / LOG ONLY (NO STOCK MODIFICATION)
    # ---------------------------------------------------------
    def _check_lots(self, line):

        product = line.product_id

        for lot_line in line.pack_lot_ids:

            lot = self.env["stock.lot"].search([
                ("name", "=", lot_line.lot_name),
                ("product_id", "=", product.id),
            ], limit=1)

            if not lot:
                _logger.warning("Lot not found: %s", lot_line.lot_name)
                continue

            _logger.info(
                "POS LOT USED -> Product: %s | Lot: %s | Qty: %s",
                product.display_name,
                lot.name,
                line.qty,
            )