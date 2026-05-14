/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Product } from "@point_of_sale/app/store/models";

patch(Product.prototype, {
    async getAddProductOptions(code) {

        // 🔥 skip original popup logic
        let quantity = 1;
        let draftPackLotLines = null;

        // uniquement produits trackés
        if (this.isTracked()) {

            try {
                const lots = await this.env.services.orm.call(
                    "stock.lot",
                    "get_fefo_lots",
                    [],
                    {
                        product_id: this.id,
                    }
                );

                if (lots.length) {
                    const selectedLot = lots[0];

                    draftPackLotLines = {
                        modifiedPackLotLines: {},
                        newPackLotLines: [
                            {
                                lot_name: selectedLot.lot_name,
                            },
                        ],
                    };
                }

            } catch (error) {
                console.error("FEFO ERROR:", error);
            }
        }

        // 🔥 return directly → PAS DE POPUP
        return {
            draftPackLotLines,
            quantity,
            price_extra: 0,
            attribute_value_ids: [],
            attribute_custom_values: {},
            comboLines: [],
        };
    },
});