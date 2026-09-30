from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EstateDashboard(models.AbstractModel):
    _name = "estate.dashboard"
    _description = "Données du tableau de bord immobilier"

    @api.model
    def get_data(
        self,
        period="month",
        date_from=False,
        date_to=False,
        property_id=False,
        property_type_id=False,
        manager_id=False,
    ):
        """Return dashboard data scoped by the selected global filters."""
        today = fields.Date.today()
        period_starts = {
            "today": today,
            "week": today - timedelta(days=today.weekday()),
            "month": today.replace(day=1),
            "year": today.replace(month=1, day=1),
        }
        date_from = fields.Date.to_date(date_from) if date_from else period_starts.get(period, today.replace(day=1))
        date_to = fields.Date.to_date(date_to) if date_to else today
        if date_to < date_from:
            raise ValidationError(_("La date de fin doit être postérieure ou égale à la date de début."))

        Property = self.env["estate.property"]
        property_domain = [("state", "=", "active")]
        if property_id:
            property_domain.append(("id", "=", int(property_id)))
        if property_type_id:
            property_domain.append(("property_type_id", "=", int(property_type_id)))
        if manager_id:
            property_domain.append(("manager_id", "=", int(manager_id)))
        selected_properties = Property.search(property_domain)
        selected_property_ids = selected_properties.ids
        schedule_property_domain = [("property_id", "in", selected_property_ids)]
        invoice_property_domain = [("estate_property_id", "in", selected_property_ids)]
        period_domain = [
            ("date_due", ">=", date_from),
            ("date_due", "<=", date_to),
            ("state", "!=", "cancelled"),
        ]
        Unit = self.env["estate.unit"]
        Lease = self.env["estate.lease"]
        Schedule = self.env["estate.rent.schedule"]
        Invoice = self.env["account.move"]
        Charge = self.env["estate.charge"]
        Deposit = self.env["estate.deposit"]
        Maintenance = self.env["maintenance.request"]

        units = Unit.search(schedule_property_domain)
        schedules = Schedule.search(schedule_property_domain + period_domain)
        invoice_domain = invoice_property_domain + [
            ("estate_schedule_id", "!=", False),
            ("estate_schedule_id.state", "!=", "cancelled"),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ]
        posted_invoices = Invoice.search(invoice_domain)
        open_invoices = posted_invoices.filtered(lambda item: item.amount_residual > 0.01)
        late_invoices = open_invoices.filtered(lambda item: item.invoice_date_due and item.invoice_date_due < today)
        unpaid_alerts = Invoice.search(
            invoice_domain + [("amount_residual", ">", 0)],
            limit=50,
            order="invoice_date_due asc, id",
        )
        active_leases = Lease.search(schedule_property_domain + [("state", "=", "active")])
        expiring_leases = Lease.search(
            schedule_property_domain
            + [
                ("state", "=", "active"),
                ("date_end", ">=", date_from),
                ("date_end", "<=", date_to),
            ],
            limit=50,
            order="date_end, id",
        )
        available_units = Unit.search(schedule_property_domain + [("state", "=", "available")], limit=50, order="property_id, name")
        charges = Charge.search([
            ("property_id", "in", selected_property_ids),
            ("state", "in", ["confirmed", "billed", "paid"]),
            ("date", ">=", date_from), ("date", "<=", date_to),
        ])
        deposits = Deposit.search(
            [("lease_id.property_id", "in", selected_property_ids), ("date", ">=", date_from), ("date", "<=", date_to)]
        )
        maintenance_requests = Maintenance.search([
            ("estate_property_id", "in", selected_property_ids),
            ("archive", "=", False),
        ])
        open_maintenance = maintenance_requests.filtered(lambda request: not request.stage_id.done)

        # Lease schedules are the forecast source. Financial execution is read
        # from the posted customer invoices and their accounting residuals.
        expected = sum(schedules.mapped("total_amount"))
        invoiced = sum(posted_invoices.mapped("amount_total_signed"))
        collection_partials = self._collected_partials(
            date_from,
            date_to,
            selected_property_ids,
        )
        collected = sum(collection_partials.mapped("amount"))
        receivable = sum(open_invoices.mapped("amount_residual_signed"))
        late_amount = sum(late_invoices.mapped("amount_residual_signed"))
        debtor_ids = open_invoices.mapped("partner_id").ids
        charge_total = sum(charges.mapped("amount"))
        deposit_required = sum(deposits.mapped("amount_required"))
        deposit_paid = sum(deposits.mapped("amount_paid"))
        deposit_balance = sum(deposits.mapped("amount_balance"))

        finance_timeline = self._finance_timeline(
            schedules,
            posted_invoices,
            collection_partials,
            charges,
            date_from,
            date_to,
            period,
        )
        tenant_debts = self._tenant_debts(open_invoices)
        revenue = {
            "properties": self._revenue_breakdown(posted_invoices, "estate_property_id"),
            "units": self._revenue_breakdown(posted_invoices, "estate_unit_id"),
            "tenants": self._revenue_breakdown(posted_invoices, "partner_id"),
        }

        all_properties = Property.search([( "state", "=", "active")])
        property_types = all_properties.mapped("property_type_id").sorted("name")
        managers = all_properties.mapped("manager_id").sorted("name")
        analysis = self._build_analysis(
            selected_properties,
            units,
            schedules,
            open_invoices,
            charges,
            deposits,
            maintenance_requests,
            open_maintenance,
            active_leases,
            collection_partials,
            date_from,
            date_to,
            today,
        )

        return {
            "currency": self.env.company.currency_id.symbol,
            "today": str(today),
            "date_from": str(date_from),
            "date_to": str(date_to),
            "properties": [{"id": item.id, "name": item.name} for item in all_properties],
            "property_types": [{"id": item.id, "name": item.name} for item in property_types],
            "managers": [{"id": item.id, "name": item.name} for item in managers],
            "kpis": {
                "property_count": len(selected_properties),
                "unit_count": len(units),
                "occupied": len(units.filtered(lambda item: item.state == "occupied")),
                "available": len(available_units),
                "maintenance": len(units.filtered(lambda item: item.state == "maintenance")),
                "occupancy_rate": (100 * len(units.filtered(lambda item: item.state == "occupied")) / len(units)) if units else 0,
                "active_leases": len(active_leases),
                "expected": expected,
                "revenue": invoiced,
                "invoiced": invoiced,
                "collected": collected,
                "outstanding": receivable,
                "receivable": receivable,
                "debtor_count": len(debtor_ids),
                "debtor_ids": debtor_ids,
                "late_amount": late_amount,
                "late_count": len(late_invoices),
                "invoice_unpaid_amount": receivable,
                "invoice_unpaid_count": len(open_invoices),
                "recovery_rate": (100 * collected / invoiced) if invoiced else 0,
                "expiring_lease_count": len(expiring_leases),
                "charge_total": charge_total,
                "deposit_required": deposit_required,
                "deposit_paid": deposit_paid,
                "deposit_balance": deposit_balance,
                "maintenance_open_count": len(open_maintenance),
                "maintenance_urgent_count": len(open_maintenance.filtered(lambda request: request.priority == "3")),
            },
            "charts": {
                "finance": finance_timeline,
                "occupancy": [
                    {
                        "state": state,
                        "label": label,
                        "value": len(units.filtered(lambda item, value=state: item.state == value)),
                    }
                    for state, label in [
                        ("occupied", "Occupées"),
                        ("available", "Disponibles"),
                        ("maintenance", "Maintenance"),
                        ("reserved", "Réservées"),
                    ]
                ],
            },
            "finance": {
                "billing_rate": (100 * invoiced / expected) if expected else 0,
                "collection_rate": (100 * collected / invoiced) if invoiced else 0,
                "collection_vs_expected": (100 * collected / expected) if expected else 0,
                "to_invoice": max(expected - invoiced, 0),
                "collection_gap": max(invoiced - collected, 0),
            },
            "revenue": revenue,
            "analysis": analysis,
            "alerts": {
                "unpaid": self._invoice_lines(unpaid_alerts),
                "tenant_debts": tenant_debts,
                "expiring": self._lease_lines(expiring_leases),
                "available": self._unit_lines(available_units),
            },
        }

    def _finance_timeline(
        self,
        schedules,
        invoices,
        collection_partials,
        charges,
        date_from,
        date_to,
        period,
    ):
        """Build a compact financial timeline at a meaningful time scale.

        Day bands are useful for short operational ranges; a yearly dashboard is
        readable by month; long custom ranges are condensed by year.  All three
        financial sources are already scoped by the global dashboard filters.
        """
        duration = (date_to - date_from).days + 1
        if period in ("today", "week", "month") or duration <= 31:
            granularity = "day"
            granularity_label = _("jours")
        elif duration <= 731:
            granularity = "month"
            granularity_label = _("mois")
        else:
            granularity = "year"
            granularity_label = _("années")

        values = []
        keys = {}
        cursor = date_from
        while cursor <= date_to:
            if granularity == "day":
                range_start = range_end = cursor
                key = cursor.isoformat()
                label = cursor.strftime("%d/%m")
                next_cursor = cursor + timedelta(days=1)
            elif granularity == "month":
                month_start = cursor.replace(day=1)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                range_start = max(month_start, date_from)
                range_end = min(month_end, date_to)
                key = "%04d-%02d" % (month_start.year, month_start.month)
                label = month_start.strftime("%m/%Y")
                next_cursor = month_end + timedelta(days=1)
            else:
                year_start = date(cursor.year, 1, 1)
                year_end = date(cursor.year, 12, 31)
                range_start = max(year_start, date_from)
                range_end = min(year_end, date_to)
                key = str(cursor.year)
                label = str(cursor.year)
                next_cursor = date(cursor.year + 1, 1, 1)

            keys[key] = len(values)
            values.append({
                "label": label,
                "date_from": str(range_start),
                "date_to": str(range_end),
                "expected": 0.0,
                "invoiced": 0.0,
                "collected": 0.0,
                "charges": 0.0,
                "outstanding": 0.0,
                "cumulative_collected": 0.0,
            })
            cursor = next_cursor

        def get_key(value):
            if granularity == "day":
                return value.isoformat()
            if granularity == "month":
                return "%04d-%02d" % (value.year, value.month)
            return str(value.year)

        for schedule in schedules:
            key = get_key(schedule.date_due)
            if key in keys:
                values[keys[key]]["expected"] += schedule.total_amount
        for invoice in invoices:
            key = get_key(invoice.invoice_date)
            if key in keys:
                values[keys[key]]["invoiced"] += invoice.amount_total_signed
                values[keys[key]]["outstanding"] += max(
                    invoice.amount_residual_signed,
                    0.0,
                )
        for partial in collection_partials:
            key = get_key(partial.max_date)
            if key in keys:
                values[keys[key]]["collected"] += partial.amount
        for charge in charges:
            key = get_key(charge.date)
            if key in keys:
                values[keys[key]]["charges"] += charge.amount

        cumulative_collected = 0.0
        for value in values:
            cumulative_collected += value["collected"]
            value["cumulative_collected"] = cumulative_collected

        max_amount = max(
            [1.0]
            + [value["expected"] for value in values]
            + [value["invoiced"] for value in values]
            + [value["collected"] for value in values]
            + [value["charges"] for value in values]
            + [value["outstanding"] for value in values]
            + [value["cumulative_collected"] for value in values]
        )
        return {
            "granularity": granularity,
            "granularity_label": granularity_label,
            "items": values,
            "max_amount": max_amount,
        }

    def _build_analysis(
        self,
        properties,
        units,
        schedules,
        open_invoices,
        charges,
        deposits,
        maintenance_requests,
        open_maintenance,
        active_leases,
        collection_partials,
        date_from,
        date_to,
        today,
    ):
        """Prepare the compact operational analyses displayed on the dashboard."""
        def segments(values):
            total = sum(max(value["value"], 0.0) for value in values)
            return [
                {
                    **value,
                    "percentage": round(100 * value["value"] / total, 1) if total else 0.0,
                }
                for value in values
            ]

        unit_states = {
            "occupied": len(units.filtered(lambda unit: unit.state == "occupied")),
            "available": len(units.filtered(lambda unit: unit.state == "available")),
            "maintenance": len(units.filtered(lambda unit: unit.state == "maintenance")),
            "reserved": len(units.filtered(lambda unit: unit.state == "reserved")),
        }
        unit_segments = segments([
            {"key": "occupied", "label": _("Occupées"), "value": unit_states["occupied"]},
            {"key": "available", "label": _("Disponibles"), "value": unit_states["available"]},
            {"key": "maintenance", "label": _("Maintenance"), "value": unit_states["maintenance"]},
            {"key": "reserved", "label": _("Réservées"), "value": unit_states["reserved"]},
        ])

        rent_expected = sum(schedules.mapped("rent_amount"))
        recoverable_charges = sum(schedules.mapped("charge_amount"))
        other_revenue = sum(schedules.mapped("penalty_amount")) - sum(
            schedules.mapped("discount_amount")
        )
        revenue_segments = segments([
            {"key": "rent", "label": _("Loyers attendus"), "value": rent_expected},
            {"key": "charge", "label": _("Charges récupérables"), "value": recoverable_charges},
            {"key": "other", "label": _("Autres revenus"), "value": max(other_revenue, 0.0)},
        ])

        property_occupancy = []
        for property_record in properties[:6]:
            property_units = units.filtered(
                lambda unit, property_id=property_record.id: unit.property_id.id == property_id
            )
            occupied = len(property_units.filtered(lambda unit: unit.state == "occupied"))
            property_occupancy.append({
                "id": property_record.id,
                "name": property_record.name,
                "occupied": occupied,
                "total": len(property_units),
                "percentage": round(100 * occupied / len(property_units), 1) if property_units else 0.0,
            })

        aging_values = {
            "0_7": {"label": _("0 – 7 jours"), "value": 0.0, "count": 0},
            "8_15": {"label": _("8 – 15 jours"), "value": 0.0, "count": 0},
            "16_30": {"label": _("16 – 30 jours"), "value": 0.0, "count": 0},
            "30_plus": {"label": _("+ 30 jours"), "value": 0.0, "count": 0},
        }
        for invoice in open_invoices:
            days = max((today - invoice.invoice_date_due).days, 0) if invoice.invoice_date_due else 0
            key = "0_7" if days <= 7 else "8_15" if days <= 15 else "16_30" if days <= 30 else "30_plus"
            aging_values[key]["value"] += max(invoice.amount_residual_signed, 0.0)
            aging_values[key]["count"] += 1
        aging = [aging_values[key] | {"key": key} for key in ("30_plus", "16_30", "8_15", "0_7")]

        charge_labels = dict(self.env["estate.charge"]._fields["charge_type"].selection)
        charge_values = defaultdict(float)
        for charge in charges:
            charge_values[charge.charge_type] += charge.amount
        charge_breakdown = [
            {
                "key": key,
                "label": charge_labels.get(key, key),
                "value": value,
            }
            for key, value in sorted(charge_values.items(), key=lambda item: -item[1])[:6]
        ]

        deposit_segments = segments([
            {"key": "paid", "label": _("Versées"), "value": sum(deposits.mapped("amount_paid"))},
            {"key": "unpaid", "label": _("À verser"), "value": sum(deposits.mapped("amount_balance"))},
        ])
        urgent_maintenance = open_maintenance.filtered(lambda request: request.priority == "3")
        completed_maintenance = maintenance_requests.filtered(lambda request: request.stage_id.done)
        planned_maintenance = open_maintenance - urgent_maintenance
        maintenance_segments = segments([
            {"key": "urgent", "label": _("Urgentes"), "value": len(urgent_maintenance)},
            {"key": "planned", "label": _("Planifiées"), "value": len(planned_maintenance)},
            {"key": "done", "label": _("Terminées"), "value": len(completed_maintenance)},
        ])

        leases = self.env["estate.lease"].search([
            ("property_id", "in", properties.ids),
        ])
        lease_labels = {
            "active": _("Actifs"),
            "submitted": _("À valider"),
            "expired": _("Expirés"),
            "terminated": _("Résiliés"),
        }
        lease_statuses = [
            {
                "key": key,
                "label": label,
                "value": len(leases.filtered(lambda lease, value=key: lease.state == value)),
            }
            for key, label in lease_labels.items()
        ]
        recent_collections = []
        for partial in collection_partials.sorted(
            key=lambda reconciliation: reconciliation.max_date or date.min,
            reverse=True,
        )[:8]:
            invoice = partial.debit_move_id.move_id
            recent_collections.append({
                "id": invoice.id,
                "invoice_id": invoice.id,
                "date": str(partial.max_date),
                "tenant": invoice.partner_id.name,
                "unit": invoice.estate_unit_id.name,
                "amount": partial.amount,
            })

        return {
            "revenue_segments": revenue_segments,
            "unit_segments": unit_segments,
            "property_occupancy": property_occupancy,
            "aging": aging,
            "charges": charge_breakdown,
            "deposits": deposit_segments,
            "maintenance": maintenance_segments,
            "maintenance_total": len(open_maintenance),
            "lease_statuses": lease_statuses,
            "recent_collections": recent_collections,
            "active_lease_count": len(active_leases),
            "date_from": str(date_from),
            "date_to": str(date_to),
        }

    def _collected_amount(self, date_from, date_to, property_ids=False):
        return sum(self._collected_partials(date_from, date_to, property_ids).mapped("amount"))

    def _collected_partials(self, date_from, date_to, property_ids=False):
        partial_domain = [
            ("max_date", ">=", date_from),
            ("max_date", "<=", date_to),
            ("debit_move_id.move_id.move_type", "=", "out_invoice"),
            ("debit_move_id.move_id.state", "=", "posted"),
            ("debit_move_id.move_id.estate_schedule_id", "!=", False),
            ("debit_move_id.move_id.estate_schedule_id.state", "!=", "cancelled"),
        ]
        if property_ids:
            partial_domain.append(
                ("debit_move_id.move_id.estate_property_id", "in", property_ids)
            )
        return self.env["account.partial.reconcile"].search(partial_domain)

    def _revenue_breakdown(self, invoices, relation_field):
        values = defaultdict(lambda: {"id": False, "name": "", "count": 0, "invoiced": 0.0, "residual": 0.0})
        for invoice in invoices:
            related_record = invoice[relation_field]
            if not related_record:
                continue
            item = values[related_record.id]
            item["id"] = related_record.id
            item["name"] = related_record.display_name
            item["count"] += 1
            item["invoiced"] += invoice.amount_total_signed
            item["residual"] += invoice.amount_residual_signed
        for item in values.values():
            item["recovery_rate"] = (
                100 * (item["invoiced"] - item["residual"]) / item["invoiced"] if item["invoiced"] else 0
            )
        return sorted(values.values(), key=lambda item: (-item["invoiced"], item["name"]))[:50]

    def _tenant_debts(self, invoices):
        debts = defaultdict(lambda: {"id": False, "name": "", "amount": 0.0, "count": 0})
        for invoice in invoices:
            item = debts[invoice.partner_id.id]
            item["id"] = invoice.partner_id.id
            item["name"] = invoice.partner_id.name
            item["amount"] += invoice.amount_residual_signed
            item["count"] += 1
        return sorted(debts.values(), key=lambda item: (-item["amount"], item["name"]))[:50]

    def _invoice_lines(self, records):
        today = fields.Date.today()
        return [
            {
                "id": record.id,
                "tenant": record.partner_id.name,
                "unit": record.estate_unit_id.name,
                "due_date": str(record.invoice_date_due),
                "late_days": max((today - record.invoice_date_due).days, 0) if record.invoice_date_due else 0,
                "amount": record.amount_residual_signed,
            }
            for record in records
        ]

    def _lease_lines(self, records):
        today = fields.Date.today()
        return [
            {
                "id": record.id,
                "name": record.name,
                "tenant": record.tenant_id.name,
                "unit": record.unit_id.name,
                "date_end": str(record.date_end),
                "days": (record.date_end - today).days,
            }
            for record in records
        ]

    def _unit_lines(self, records):
        return [
            {
                "id": record.id,
                "property": record.property_id.name,
                "name": record.name,
                "type": record.unit_type_id.name,
                "rent": record.indicative_rent,
            }
            for record in records
        ]
