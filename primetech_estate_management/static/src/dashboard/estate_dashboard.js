/** @odoo-module **/
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useExternalListener,
    useState,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class EstateDashboard extends Component {
    static template = "primetech_estate_management.EstateDashboard";

    setup() {
        // Template event handlers are invoked without the component as their
        // implicit receiver. Bind them once so that every KPI and filter keeps
        // access to the reactive state and action services.
        [
            "load",
            "togglePeriodMenu",
            "togglePropertyMenu",
            "togglePropertyTypeMenu",
            "toggleManagerMenu",
            "closeGlobalFilters",
            "selectPeriod",
            "selectProperty",
            "selectPropertyType",
            "selectManager",
            "onCustomDateChange",
            "customDates",
            "resetFilters",
            "openProperties",
            "openUnits",
            "openPeriodSchedules",
            "openFinanceMetric",
            "openReceivables",
            "openLateSchedules",
            "openUnpaidInvoices",
            "openDebtors",
            "openCollectionMonth",
            "openFinanceBucket",
            "toggleFinanceSeries",
            "openCharges",
            "openDeposits",
            "openMaintenance",
            "openLeaseStatus",
            "openAging",
            "openPropertyOccupancy",
            "openRevenueSegment",
            "openMaintenanceStatus",
            "openChargeType",
            "openTenantReceivables",
            "openPropertyRevenue",
            "openUnitRevenue",
            "openTenantRevenue",
            "openLease",
            "openSchedule",
            "openInvoice",
            "openUnit",
        ].forEach((methodName) => {
            this[methodName] = this[methodName].bind(this);
        });

        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dashboardStateKey = "primetech_estate_management.dashboard.state";
        const savedState = this._readDashboardState();
        this.state = useState({
            period: savedState.period || "month",
            periodOpen: false,
            propertyOpen: false,
            propertyTypeOpen: false,
            managerOpen: false,
            dateFrom: savedState.dateFrom || false,
            dateTo: savedState.dateTo || false,
            propertyId: savedState.propertyId || false,
            propertyTypeId: savedState.propertyTypeId || false,
            managerId: savedState.managerId || false,
            financeSeries: savedState.financeSeries || {
                expected: true,
                invoiced: false,
                collected: true,
                charges: false,
            },
            data: null,
            loading: true,
        });
        this.dashboardScrollTop = savedState.scrollTop || 0;
        this.loadRequestId = 0;
        useExternalListener(window, "click", this.closeGlobalFilters);
        onMounted(() => this._restoreDashboardScroll());
        onWillUnmount(() => this._saveDashboardState());
        onWillStart(() => this.load());
    }

    _readDashboardState() {
        try {
            const rawState = window.sessionStorage.getItem(this.dashboardStateKey);
            const savedState = rawState ? JSON.parse(rawState) : {};
            const validPeriods = ["today", "week", "month", "year", "custom"];
            return {
                period: validPeriods.includes(savedState.period) ? savedState.period : "month",
                dateFrom: savedState.dateFrom || false,
                dateTo: savedState.dateTo || false,
                propertyId: Number(savedState.propertyId) || false,
                propertyTypeId: Number(savedState.propertyTypeId) || false,
                managerId: Number(savedState.managerId) || false,
                financeSeries: {
                    expected: savedState.financeSeries?.expected !== false,
                    invoiced: false,
                    collected: savedState.financeSeries?.collected !== false,
                    charges: Boolean(savedState.financeSeries?.charges),
                },
                scrollTop: Math.max(0, Number(savedState.scrollTop) || 0),
            };
        } catch {
            return {};
        }
    }

    _saveDashboardState() {
        const dashboard = document.querySelector(".o_estate_dashboard");
        if (dashboard) {
            this.dashboardScrollTop = dashboard.scrollTop;
        }
        try {
            window.sessionStorage.setItem(
                this.dashboardStateKey,
                JSON.stringify({
                    period: this.state.period,
                    dateFrom: this.state.dateFrom || false,
                    dateTo: this.state.dateTo || false,
                propertyId: this.state.propertyId || false,
                propertyTypeId: this.state.propertyTypeId || false,
                managerId: this.state.managerId || false,
                    financeSeries: this.state.financeSeries,
                    scrollTop: this.dashboardScrollTop,
                })
            );
        } catch {
            // A restrictive browser mode must not prevent dashboard navigation.
        }
    }

    _restoreDashboardScroll() {
        if (!this.dashboardScrollTop) {
            return;
        }
        window.requestAnimationFrame(() => {
            const dashboard = document.querySelector(".o_estate_dashboard");
            if (dashboard) {
                dashboard.scrollTop = this.dashboardScrollTop;
            }
        });
    }

    get periodOptions() {
        return [
            { value: "today", label: "Aujourd’hui" },
            { value: "week", label: "Cette semaine" },
            { value: "month", label: "Ce mois" },
            { value: "year", label: "Cette année" },
            { value: "custom", label: "Période" },
        ];
    }

    get selectedPeriodLabel() {
        return this.periodOptions.find((option) => option.value === this.state.period)?.label || "Ce mois";
    }

    get selectedPropertyLabel() {
        if (!this.state.propertyId) {
            return "Tous les immeubles";
        }
        return this.state.data.properties.find((property) => property.id === this.state.propertyId)?.name || "Tous les immeubles";
    }

    get selectedPropertyTypeLabel() {
        if (!this.state.propertyTypeId) {
            return "Tous les types";
        }
        return this.state.data.property_types.find((type) => type.id === this.state.propertyTypeId)?.name || "Tous les types";
    }

    get selectedManagerLabel() {
        if (!this.state.managerId) {
            return "Tous les gestionnaires";
        }
        return this.state.data.managers.find((manager) => manager.id === this.state.managerId)?.name || "Tous les gestionnaires";
    }

    get dashboardScopeLabel() {
        if (this.state.propertyId) {
            return this.selectedPropertyLabel;
        }
        if (this.state.propertyTypeId) {
            return `Type : ${this.selectedPropertyTypeLabel}`;
        }
        if (this.state.managerId) {
            return `Gestionnaire : ${this.selectedManagerLabel}`;
        }
        return "Tous les immeubles";
    }

    get dateRangeLabel() {
        if (!this.state.data) {
            return "";
        }
        const formatDate = (value) => new Intl.DateTimeFormat("fr-FR", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        }).format(new Date(`${value}T12:00:00`));
        const { date_from, date_to } = this.state.data;
        return date_from === date_to
            ? `Le ${formatDate(date_from)}`
            : `Du ${formatDate(date_from)} au ${formatDate(date_to)}`;
    }

    async load() {
        const requestId = ++this.loadRequestId;
        this.state.loading = true;
        try {
            const data = await this.orm.call("estate.dashboard", "get_data", [], {
                period: this.state.period,
                date_from: this.state.dateFrom || false,
                date_to: this.state.dateTo || false,
                property_id: this.state.propertyId || false,
                property_type_id: this.state.propertyTypeId || false,
                manager_id: this.state.managerId || false,
            });
            if (requestId === this.loadRequestId) {
                this.state.data = data;
                this._saveDashboardState();
                this._restoreDashboardScroll();
            }
        } finally {
            if (requestId === this.loadRequestId) {
                this.state.loading = false;
            }
        }
    }

    togglePeriodMenu() {
        this.state.periodOpen = !this.state.periodOpen;
        this.state.propertyOpen = false;
        this.state.propertyTypeOpen = false;
        this.state.managerOpen = false;
    }

    togglePropertyMenu() {
        this.state.propertyOpen = !this.state.propertyOpen;
        this.state.periodOpen = false;
        this.state.propertyTypeOpen = false;
        this.state.managerOpen = false;
    }

    togglePropertyTypeMenu() {
        this.state.propertyTypeOpen = !this.state.propertyTypeOpen;
        this.state.periodOpen = false;
        this.state.propertyOpen = false;
        this.state.managerOpen = false;
    }

    toggleManagerMenu() {
        this.state.managerOpen = !this.state.managerOpen;
        this.state.periodOpen = false;
        this.state.propertyOpen = false;
        this.state.propertyTypeOpen = false;
    }

    closeGlobalFilters() {
        this.state.periodOpen = false;
        this.state.propertyOpen = false;
        this.state.propertyTypeOpen = false;
        this.state.managerOpen = false;
    }

    async selectPeriod(period) {
        this.state.period = period;
        this.state.periodOpen = false;
        if (period === "custom") {
            // Keep a valid range visible until the user chooses the final dates.
            this.state.dateFrom = this.state.data.date_from;
            this.state.dateTo = this.state.data.date_to;
            return;
        }
        this.state.dateFrom = false;
        this.state.dateTo = false;
        await this.load();
    }

    async selectProperty(propertyId) {
        this.state.propertyId = propertyId || false;
        this.state.propertyOpen = false;
        await this.load();
    }

    async selectPropertyType(propertyTypeId) {
        this.state.propertyTypeId = propertyTypeId || false;
        this.state.propertyTypeOpen = false;
        this.state.propertyId = false;
        await this.load();
    }

    async selectManager(managerId) {
        this.state.managerId = managerId || false;
        this.state.managerOpen = false;
        this.state.propertyId = false;
        await this.load();
    }

    async onCustomDateChange(fieldName, event) {
        this.state[fieldName] = event.target.value || false;
        if (this.state.dateFrom && this.state.dateTo) {
            await this.customDates();
        }
    }

    async customDates() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            this.notification.add("Sélectionnez une date de début et une date de fin.", { type: "warning" });
            return;
        }
        if (this.state.dateFrom > this.state.dateTo) {
            this.notification.add("La date de fin doit être postérieure ou égale à la date de début.", { type: "danger" });
            return;
        }
        this.closeGlobalFilters();
        await this.load();
    }

    async resetFilters() {
        this.state.period = "month";
        this.closeGlobalFilters();
        this.state.dateFrom = false;
        this.state.dateTo = false;
        this.state.propertyId = false;
        this.state.propertyTypeId = false;
        this.state.managerId = false;
        this.dashboardScrollTop = 0;
        await this.load();
    }

    propertyDomain(fieldName = "property_id") {
        const domain = [];
        if (this.state.propertyId) {
            domain.push([fieldName, "=", Number(this.state.propertyId)]);
            return domain;
        }
        if (this.state.propertyTypeId) {
            domain.push([`${fieldName}.property_type_id`, "=", Number(this.state.propertyTypeId)]);
        }
        if (this.state.managerId) {
            domain.push([`${fieldName}.manager_id`, "=", Number(this.state.managerId)]);
        }
        return domain;
    }

    selectedPropertyDomain() {
        const domain = [];
        if (this.state.propertyId) {
            domain.push(["id", "=", Number(this.state.propertyId)]);
        }
        if (this.state.propertyTypeId) {
            domain.push(["property_type_id", "=", Number(this.state.propertyTypeId)]);
        }
        if (this.state.managerId) {
            domain.push(["manager_id", "=", Number(this.state.managerId)]);
        }
        return domain;
    }

    periodScheduleDomain(filters = [], dateFrom = this.state.data.date_from, dateTo = this.state.data.date_to) {
        return [
            ...this.propertyDomain(),
            ["date_due", ">=", dateFrom],
            ["date_due", "<=", dateTo],
            ["state", "!=", "cancelled"],
            ...filters,
        ];
    }

    openList(name, model, domain = [], context = {}) {
        this._saveDashboardState();
        return this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: [[false, "list"], [false, "form"]],
            view_mode: "list,form",
            domain,
            context,
            target: "current",
        });
    }

    openRecord(name, model, recordId) {
        this._saveDashboardState();
        return this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            res_id: recordId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    openProperties() {
        return this.openList("Immeubles", "estate.property", this.selectedPropertyDomain());
    }

    openUnits(unitState = false) {
        // Direct Owl handlers receive the click event as first argument.
        // Keep the action domain valid even if this method is reused directly.
        if (typeof unitState !== "string") {
            unitState = false;
        }
        const domain = this.propertyDomain();
        if (unitState) {
            domain.push(["state", "=", unitState]);
        }
        const labels = {
            occupied: "Locaux occupés",
            available: "Locaux disponibles",
            maintenance: "Locaux en maintenance",
            reserved: "Locaux réservés",
        };
        return this.openList(labels[unitState] || "Locaux", "estate.unit", domain);
    }

    openPeriodSchedules(
        filters = [],
        title = "Échéances de la période",
        context = {},
        dateFrom = this.state.data.date_from,
        dateTo = this.state.data.date_to
    ) {
        return this.openList(title, "estate.rent.schedule", this.periodScheduleDomain(filters, dateFrom, dateTo), context);
    }

    openFinanceMetric(metric) {
        if (metric === "invoiced") {
            return this.openInvoicedInvoices();
        }
        if (metric === "collected") {
            return this.openPayments();
        }
        if (metric === "outstanding") {
            return this.openReceivables();
        }
        const metrics = {
            expected: { title: "Échéances attendues", filters: [] },
        };
        const selection = metrics[metric] || metrics.expected;
        return this.openPeriodSchedules(selection.filters, selection.title);
    }

    invoiceDomain(filters = [], dateFrom = this.state.data.date_from, dateTo = this.state.data.date_to) {
        return [
            ...this.propertyDomain("estate_property_id"),
            ["estate_schedule_id", "!=", false],
            ["invoice_date", ">=", dateFrom],
            ["invoice_date", "<=", dateTo],
            ["estate_schedule_id.state", "!=", "cancelled"],
            ["move_type", "=", "out_invoice"],
            ["state", "!=", "cancel"],
            ...filters,
        ];
    }

    openInvoicedInvoices(
        dateFrom = this.state.data.date_from,
        dateTo = this.state.data.date_to,
        title = "Factures de loyers"
    ) {
        return this.openList(
            title,
            "account.move",
            this.invoiceDomain([["state", "=", "posted"]], dateFrom, dateTo),
            { default_move_type: "out_invoice" }
        );
    }

    paymentDomain(dateFrom = this.state.data.date_from, dateTo = this.state.data.date_to) {
        return [
            ["payment_type", "=", "inbound"],
            ["state", "=", "paid"],
            ["date", ">=", dateFrom],
            ["date", "<=", dateTo],
            ["reconciled_invoice_ids.estate_schedule_id", "!=", false],
            ["reconciled_invoice_ids.estate_schedule_id.state", "!=", "cancelled"],
            ...this.propertyDomain("reconciled_invoice_ids.estate_property_id"),
        ];
    }

    openPayments(dateFrom = this.state.data.date_from, dateTo = this.state.data.date_to, title = "Encaissements de loyers") {
        return this.openList(
            title,
            "account.payment",
            this.paymentDomain(dateFrom, dateTo),
            { default_payment_type: "inbound", default_partner_type: "customer" }
        );
    }

    openCharges(
        dateFrom = this.state.data.date_from,
        dateTo = this.state.data.date_to,
        title = "Charges de la période"
    ) {
        if (typeof dateFrom !== "string") {
            dateFrom = this.state.data.date_from;
            dateTo = this.state.data.date_to;
            title = "Charges de la période";
        }
        return this.openList(
            title,
            "estate.charge",
            [
                ...this.propertyDomain("property_id"),
                ["state", "in", ["confirmed", "billed", "paid"]],
                ["date", ">=", dateFrom],
                ["date", "<=", dateTo],
            ]
        );
    }

    openDeposits() {
        return this.openList(
            "Cautions locatives",
            "estate.deposit",
            this.propertyDomain("lease_id.property_id")
        );
    }

    openMaintenance(filters = [], title = "Maintenances") {
        if (!Array.isArray(filters)) {
            filters = [];
        }
        return this.openList(
            title,
            "maintenance.request",
            [...this.propertyDomain("estate_property_id"), ...filters]
        );
    }

    openLeaseStatus(state) {
        const labels = {
            active: "Contrats actifs",
            submitted: "Contrats à valider",
            expired: "Contrats expirés",
            terminated: "Contrats résiliés",
        };
        return this.openList(
            labels[state] || "Contrats de bail",
            "estate.lease",
            [...this.propertyDomain("property_id"), ["state", "=", state]]
        );
    }

    openAging(bucket) {
        const today = new Date(`${this.state.data.today}T12:00:00`);
        const toDate = (days) => {
            const value = new Date(today);
            value.setDate(value.getDate() - days);
            return value.toISOString().slice(0, 10);
        };
        const filters = {
            "0_7": [["invoice_date_due", ">=", toDate(7)]],
            "8_15": [["invoice_date_due", ">=", toDate(15)], ["invoice_date_due", "<", toDate(7)]],
            "16_30": [["invoice_date_due", ">=", toDate(30)], ["invoice_date_due", "<", toDate(15)]],
            "30_plus": [["invoice_date_due", "<", toDate(30)]],
        };
        return this.openUnpaidInvoices(
            "Impayés par ancienneté",
            filters[bucket] || []
        );
    }

    openPropertyOccupancy(propertyId) {
        return this.openList(
            "Locaux de l'immeuble",
            "estate.unit",
            [["property_id", "=", propertyId]]
        );
    }

    openRevenueSegment(key) {
        if (key === "charge") {
            return this.openCharges();
        }
        return this.openFinanceMetric("expected");
    }

    openMaintenanceStatus(key) {
        const filters = {
            urgent: [["priority", "=", "3"], ["stage_id.done", "=", false]],
            planned: [["priority", "!=", "3"], ["stage_id.done", "=", false]],
            done: [["stage_id.done", "=", true]],
        };
        return this.openMaintenance(filters[key] || [], "Maintenances");
    }

    openChargeType(chargeType) {
        return this.openList(
            "Charges de la période",
            "estate.charge",
            [
                ...this.propertyDomain("property_id"),
                ["state", "in", ["confirmed", "billed", "paid"]],
                ["charge_type", "=", chargeType],
                ["date", ">=", this.state.data.date_from],
                ["date", "<=", this.state.data.date_to],
            ]
        );
    }

    openReceivables() {
        return this.openUnpaidInvoices("Créances locataires");
    }

    openLateSchedules() {
        return this.openUnpaidInvoices("Factures de loyers en retard", [
            ["invoice_date_due", "<", this.state.data.today],
        ]);
    }

    openUnpaidInvoices(
        title = "Factures de loyers non réglées",
        filters = [],
        dateFrom = this.state.data.date_from,
        dateTo = this.state.data.date_to
    ) {
        return this.openList(
            title,
            "account.move",
            this.invoiceDomain([
                ["state", "=", "posted"],
                ["amount_residual", ">", 0],
                ...filters,
            ], dateFrom, dateTo),
            { default_move_type: "out_invoice" }
        );
    }

    openDebtors() {
        return this.openList(
            "Locataires débiteurs",
            "res.partner",
            [
                ["id", "in", this.state.data.kpis.debtor_ids],
                ["is_estate_tenant", "=", true],
            ],
            { default_is_estate_tenant: true }
        );
    }

    openCollectionMonth(item) {
        return this.openFinanceBucket(item, "collected");
    }

    openFinanceBucket(item, metric) {
        if (metric === "expected") {
            return this.openPeriodSchedules(
                [],
                `Échéances attendues : ${item.label}`,
                {},
                item.date_from,
                item.date_to
            );
        }
        if (metric === "invoiced") {
            return this.openInvoicedInvoices(item.date_from, item.date_to, `Factures de loyers : ${item.label}`);
        }
        if (metric === "outstanding") {
            return this.openUnpaidInvoices(
                `Créances locataires : ${item.label}`,
                [],
                item.date_from,
                item.date_to
            );
        }
        if (metric === "charges") {
            return this.openCharges(
                item.date_from,
                item.date_to,
                `Charges de ${item.label}`
            );
        }
        return this.openPayments(item.date_from, item.date_to, `Encaissements de ${item.label}`);
    }

    toggleFinanceSeries(metric) {
        this.state.financeSeries[metric] = !this.state.financeSeries[metric];
        this._saveDashboardState();
    }

    openTenantReceivables(tenantId) {
        return this.openUnpaidInvoices("Créances du locataire", [["partner_id", "=", tenantId]]);
    }

    openRevenueInvoices(title, filters = []) {
        return this.openList(
            title,
            "account.move",
            this.invoiceDomain([["state", "=", "posted"], ...filters]),
            { default_move_type: "out_invoice" }
        );
    }

    openPropertyRevenue(propertyId) {
        return this.openRevenueInvoices("Chiffre d'affaires de l'immeuble", [["estate_property_id", "=", propertyId]]);
    }

    openUnitRevenue(unitId) {
        return this.openRevenueInvoices("Chiffre d'affaires du local", [["estate_unit_id", "=", unitId]]);
    }

    openTenantRevenue(tenantId) {
        return this.openRevenueInvoices("Chiffre d'affaires du locataire", [["partner_id", "=", tenantId]]);
    }

    openLease(leaseId) {
        return this.openRecord("Contrat de bail", "estate.lease", leaseId);
    }

    openSchedule(scheduleId) {
        return this.openRecord("Échéance de loyer", "estate.rent.schedule", scheduleId);
    }

    openInvoice(invoiceId) {
        return this.openRecord("Facture de loyer", "account.move", invoiceId);
    }

    openUnit(unitId) {
        return this.openRecord("Local", "estate.unit", unitId);
    }

    money(value) {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value || 0);
    }

    sumValues(items) {
        return (items || []).reduce((total, item) => total + (item.value || 0), 0);
    }

    donutStyle(items) {
        const colors = {
            rent: "var(--estate-success)",
            charge: "var(--estate-warning)",
            other: "var(--estate-info)",
            occupied: "var(--estate-success)",
            available: "var(--estate-info)",
            maintenance: "var(--estate-warning)",
            reserved: "var(--estate-primary)",
            paid: "var(--estate-success)",
            unpaid: "var(--estate-warning)",
            urgent: "var(--estate-danger)",
            planned: "var(--estate-warning)",
            done: "var(--estate-success)",
        };
        let start = 0;
        const slices = (items || []).filter((item) => item.percentage > 0).map((item) => {
            const end = Math.min(100, start + item.percentage);
            const slice = `${colors[item.key] || "var(--estate-primary)"} ${start}% ${end}%`;
            start = end;
            return slice;
        });
        if (start < 100) {
            slices.push(`var(--estate-soft) ${start}% 100%`);
        }
        return `background: conic-gradient(${slices.join(", ") || "var(--estate-soft) 0% 100%"});`;
    }

    progressStyle(value) {
        return `--estate-progress: ${Math.max(0, Math.min(100, value || 0))}%;`;
    }

    ratioStyle(value, total) {
        return this.progressStyle((100 * (value || 0)) / Math.max(1, total || 0));
    }

    financeBarHeight(item, metric) {
        const amount = Math.max(0, item[metric] || 0);
        if (!amount) {
            return 0;
        }
        const maxAmount = Math.max(
            1,
            this.state.data?.charts?.finance?.max_amount || 0
        );
        return Math.max(4, Math.min(100, (amount * 100) / maxAmount));
    }

    financeBucketTitle(item, metric) {
        const labels = {
            expected: "Loyers attendus",
            invoiced: "Facturé",
            collected: "Loyers encaissés",
            charges: "Charges",
            outstanding: "À encaisser",
        };
        const label = labels[metric] || metric;
        return `${item.label} — ${label} : ${this.money(item[metric])}`;
    }
}

registry.category("actions").add("primetech_estate_management.dashboard", EstateDashboard);
