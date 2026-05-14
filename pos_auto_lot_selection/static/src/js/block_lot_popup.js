/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Product } from "@point_of_sale/app/store/models";

patch(Product.prototype, {

    isAllowOnlyOneLot() {
        // 🔥 empêche logique popup obligatoire
        return false;
    },

    isTracked() {
        // 🔥 garde tracking mais évite popup auto POS
        return this.tracking && this.tracking !== "none";
    },
});