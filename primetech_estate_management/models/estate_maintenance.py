from odoo import api, fields, models


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    estate_unit_id = fields.Many2one(
        "estate.unit",
        string="Local",
        ondelete="set null",
        index=True,
        check_company=True,
    )
    estate_property_id = fields.Many2one(
        related="estate_unit_id.property_id",
        string="Immeuble",
        store=True,
        readonly=True,
        index=True,
    )
    estate_charge_ids = fields.One2many('estate.charge', 'maintenance_request_id', string='Coûts associés')
    estate_currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    estate_cost_amount = fields.Monetary('Coût engagé', compute='_compute_estate_cost_amount', currency_field='estate_currency_id')

    @api.depends('estate_charge_ids.amount', 'estate_charge_ids.state')
    def _compute_estate_cost_amount(self):
        for request in self:
            request.estate_cost_amount = sum(request.estate_charge_ids.filtered(
                lambda cost: cost.state in ('confirmed', 'billed', 'paid')
            ).mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        requests._sync_estate_unit_availability()
        return requests

    def write(self, vals):
        impacted_units = self.mapped("estate_unit_id")
        result = super().write(vals)
        if {"estate_unit_id", "stage_id", "archive", "maintenance_type"}.intersection(vals):
            (impacted_units | self.mapped("estate_unit_id"))._sync_from_maintenance_requests()
        return result

    def unlink(self):
        units = self.mapped("estate_unit_id")
        result = super().unlink()
        units._sync_from_maintenance_requests()
        return result

    def _sync_estate_unit_availability(self):
        self.mapped("estate_unit_id")._sync_from_maintenance_requests()

    def action_create_estate_charge(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'Nouveau coût de maintenance',
            'res_model': 'estate.charge', 'view_mode': 'form', 'target': 'current',
            'context': {
                'default_name': 'Maintenance - %s' % self.display_name,
                'default_charge_type': 'maintenance',
                'default_property_id': self.estate_property_id.id,
                'default_unit_id': self.estate_unit_id.id,
                'default_maintenance_request_id': self.id,
            },
        }


class EstateUnit(models.Model):
    _inherit = "estate.unit"

    maintenance_request_ids = fields.One2many(
        "maintenance.request",
        "estate_unit_id",
        string="Demandes de maintenance",
    )
    maintenance_request_count = fields.Integer(compute="_compute_maintenance_counts")
    maintenance_open_count = fields.Integer(compute="_compute_maintenance_counts")

    @api.depends(
        "maintenance_request_ids",
        "maintenance_request_ids.archive",
        "maintenance_request_ids.stage_id",
        "maintenance_request_ids.stage_id.done",
    )
    def _compute_maintenance_counts(self):
        for unit in self:
            requests = unit.maintenance_request_ids
            unit.maintenance_request_count = len(requests)
            unit.maintenance_open_count = len(requests.filtered(lambda request: not request.archive and not request.stage_id.done))

    def _sync_from_maintenance_requests(self):
        Request = self.env["maintenance.request"]
        Lease = self.env["estate.lease"]
        for unit in self:
            open_corrective_count = Request.search_count([
                ("estate_unit_id", "=", unit.id),
                ("maintenance_type", "=", "corrective"),
                ("archive", "=", False),
                ("stage_id.done", "=", False),
            ])
            if open_corrective_count and unit.state not in ("maintenance", "unavailable"):
                unit.state = "maintenance"
            elif not open_corrective_count and unit.state == "maintenance":
                has_active_lease = Lease.search_count([("unit_id", "=", unit.id), ("state", "=", "active")])
                unit.state = "occupied" if has_active_lease else "available"

    def action_view_maintenance_requests(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("maintenance.hr_equipment_request_action")
        action.update({
            "name": "Maintenance - %s" % self.display_name,
            "domain": [("estate_unit_id", "=", self.id)],
            "context": {
                "default_estate_unit_id": self.id,
                "default_maintenance_type": "corrective",
            },
        })
        return action

    def action_create_maintenance_request(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Nouvelle demande de maintenance",
            "res_model": "maintenance.request",
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "current",
            "context": {
                "default_name": "Maintenance - %s" % self.display_name,
                "default_company_id": self.company_id.id,
                "default_estate_unit_id": self.id,
                "default_maintenance_type": "corrective",
            },
        }
