/** @odoo-module **/

import { Component, useRef, useState, onMounted, onPatched, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class ExecutiveBoard extends Component {
    static props = { filters: { type: Object, optional: true }, refreshKey: { optional: true }, "*": true };
    setup() {
        this.actionService = useService("action");
        this.boardRef = useRef("board");
        this.stateStorageKey = "primetechExecutiveBoardState";
        this.scrollStorageKey = "primetechExecutiveBoardScroll";
        const savedState = this.loadSavedState();
        const defaultKpiFilters = { cash_period: "today", billing_period: "month", stock_scope: "all", store_period: "week", revenue_period: "week", customer_receivable_filter: "all", supplier_receivable_filter: "all" };
        this.boardCache = new Map();
        this.currentRequestId = 0;
        this.state = useState({ loading: true, period: savedState.period || "today", dateFrom: savedState.dateFrom || "", dateTo: savedState.dateTo || "", kpiCustomRanges: savedState.kpiCustomRanges || {}, clockTick: Date.now(), categoryMenuOpen: false, revenueChartHidden: Boolean(savedState.revenueChartHidden), kpiFilters: { ...defaultKpiFilters, ...(savedState.kpiFilters || {}) }, partnerSearch: { customers: savedState.partnerSearch?.customers || "", suppliers: savedState.partnerSearch?.suppliers || "" }, partnerSearchLoading: { customers: false, suppliers: false }, kpis: [], stores: [], revenue_chart: { subtitle: "Mois en cours", items: [] }, cash: [], banks: [], stock: {}, partner_balance_kpis: { customers: { rows: [] }, suppliers: { rows: [] } }, current_user: { name: "Directeur Général", status: "En ligne" }, alerts: [], quick_actions: [], activities: [], performance: [] });
        for (const key of ["cash_period", "billing_period", "store_period", "revenue_period"]) {
            if (this.state.kpiFilters[key] === "custom") this.ensureKpiCustomRange(key);
        }
        onWillStart(async () => this.loadBoard({ force: true }));
        onMounted(() => {
            this.scrollContainer = this.getScrollContainer();
            this.restoreScroll();
            this.scrollListener = () => this.scheduleSaveScroll();
            this.scrollContainer.addEventListener("scroll", this.scrollListener, { passive: true });
            this.clockInterval = setInterval(() => {
                this.state.clockTick = Date.now();
            }, 1000);
            this.refreshInterval = setInterval(() => {
                this.loadBoard({ silent: true, force: true });
            }, 30000);
            if ("ResizeObserver" in window) {
                this.kpiResizeObserver = new ResizeObserver(() => this.scheduleKpiValueFit());
                this.kpiResizeObserver.observe(this.boardRef.el.querySelector(".pt-eb-kpis"));
            } else {
                this.kpiResizeListener = () => this.scheduleKpiValueFit();
                window.addEventListener("resize", this.kpiResizeListener, { passive: true });
            }
            this.scheduleKpiValueFit();
        });
        onPatched(() => this.scheduleKpiValueFit());
        onWillUnmount(() => {
            if (this.clockInterval) {
                clearInterval(this.clockInterval);
            }
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            if (this.scrollListener) {
                this.scrollContainer?.removeEventListener("scroll", this.scrollListener);
            }
            if (this.scrollSaveTimeout) {
                clearTimeout(this.scrollSaveTimeout);
            }
            Object.values(this.partnerSearchTimeouts || {}).forEach((timeout) => clearTimeout(timeout));
            this.kpiResizeObserver?.disconnect();
            if (this.kpiResizeListener) window.removeEventListener("resize", this.kpiResizeListener);
            if (this.kpiFitFrame) cancelAnimationFrame(this.kpiFitFrame);
            this.saveDashboardState();
            if (this.boardRef.el) {
                this.saveScroll();
            }
        });
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.refreshKey !== this.props.refreshKey) {
                await this.loadBoard();
            }
        });
    }

    getBoardFilters() {
        return {
            ...(this.props.filters || {}),
            period: this.state.period,
            date_from: this.state.period === "custom" ? this.state.dateFrom : null,
            date_to: this.state.period === "custom" ? this.state.dateTo : null,
            kpi_filters: { ...this.state.kpiFilters },
            kpi_custom_ranges: Object.fromEntries(Object.entries(this.state.kpiCustomRanges).map(([key, range]) => [key, { date_from: range.dateFrom, date_to: range.dateTo }])),
            partner_search: { ...this.state.partnerSearch },
        };
    }

    getBoardCacheKey(filters = this.getBoardFilters()) {
        return JSON.stringify(filters);
    }

    rememberBoardData(key, data) {
        this.boardCache.set(key, data);
        if (this.boardCache.size > 12) {
            this.boardCache.delete(this.boardCache.keys().next().value);
        }
    }

    applyBoardData(data, options = {}) {
        Object.assign(this.state, data, { loading: false });
        for (const type of ["customers", "suppliers"]) {
            this.filterPartnerRows(type);
        }
        if (options.restoreScroll) {
            this.restoreScroll();
        }
    }

    async loadBoard(options = {}) {
        const filters = this.getBoardFilters();
        const cacheKey = this.getBoardCacheKey(filters);
        const cachedData = this.boardCache.get(cacheKey);
        if (cachedData && !options.force) {
            this.applyBoardData(cachedData, options);
            return;
        }
        if (!options.silent && !this.state.kpis.length) {
            this.state.loading = true;
        }
        const requestId = ++this.currentRequestId;
        const data = await rpc("/web/dataset/call_kw", {
            model: "primetech.dashboard",
            method: "get_executive_board",
            args: [filters],
            kwargs: {},
        });
        this.rememberBoardData(cacheKey, data);
        if (requestId === this.currentRequestId) {
            this.applyBoardData(data, options);
        }
    }

    async onPeriodChange(ev) {
        const nextPeriod = ev.target.value;
        if (nextPeriod === this.state.period) {
            return;
        }
        this.state.period = nextPeriod;
        if (nextPeriod === "custom" && (!this.state.dateFrom || !this.state.dateTo)) {
            const today = new Date();
            const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
            this.state.dateFrom ||= this.toDateInputValue(monthStart);
            this.state.dateTo ||= this.toDateInputValue(today);
        }
        this.saveDashboardState();
        await this.loadBoard({ silent: true });
    }

    async onCustomDateChange(key, ev) {
        this.state[key] = ev.target.value;
        this.saveDashboardState();
        if (this.state.dateFrom && this.state.dateTo && this.state.dateFrom <= this.state.dateTo) {
            await this.loadBoard({ silent: true });
        }
    }

    toDateInputValue(value) {
        const localDate = new Date(value.getTime() - value.getTimezoneOffset() * 60000);
        return localDate.toISOString().slice(0, 10);
    }

    async onKpiFilterChange(key, ev) {
        const nextValue = ev.target.value;
        if (nextValue === this.state.kpiFilters[key]) {
            return;
        }
        this.state.kpiFilters[key] = nextValue;
        if (nextValue === "custom") {
            this.ensureKpiCustomRange(key);
        }
        this.saveDashboardState();
        await this.loadBoard({ silent: true });
    }

    ensureKpiCustomRange(key) {
        const current = this.state.kpiCustomRanges[key] || {};
        if (!current.dateFrom || !current.dateTo) {
            const today = new Date();
            this.state.kpiCustomRanges[key] = {
                dateFrom: current.dateFrom || this.toDateInputValue(new Date(today.getFullYear(), today.getMonth(), 1)),
                dateTo: current.dateTo || this.toDateInputValue(today),
            };
        }
        return this.state.kpiCustomRanges[key];
    }

    kpiCustomRange(key) {
        return this.state.kpiCustomRanges[key] || { dateFrom: "", dateTo: "" };
    }

    async onKpiCustomDateChange(key, field, ev) {
        const range = { ...this.kpiCustomRange(key), [field]: ev.target.value };
        this.state.kpiCustomRanges[key] = range;
        this.saveDashboardState();
        if (range.dateFrom && range.dateTo && range.dateFrom <= range.dateTo) {
            await this.loadBoard({ silent: true });
        }
    }

    onPartnerSearchInput(type, ev) {
        // Read the DOM value explicitly; this avoids depending on directive
        // execution order between t-model and the input event handler.
        this.state.partnerSearch[type] = ev.target.value;
        this.partnerSearchTimeouts ||= {};
        clearTimeout(this.partnerSearchTimeouts[type]);
        this.partnerSearchTimeouts[type] = setTimeout(() => {
            this.filterPartnerRows(type);
        }, 120);
    }

    resetPartnerSearch(type) {
        this.state.partnerSearch[type] = "";
        this.filterPartnerRows(type);
    }

    filterPartnerRows(type) {
        const kpi = this.state.partner_balance_kpis[type];
        if (!kpi) return;
        const normalize = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
        const term = normalize(this.state.partnerSearch[type].trim());
        const allRows = kpi.all_rows || [];
        if (!term) {
            kpi.rows = [...(kpi.default_rows || allRows.slice(0, 4))];
            kpi.filtered_count = kpi.default_filtered_count ?? allRows.length;
            return;
        }
        const matches = allRows.filter((row) => normalize(row.partner).includes(term));
        kpi.rows = matches.slice(0, 4);
        kpi.filtered_count = matches.length;
    }

    loadSavedState() {
        try {
            return JSON.parse(sessionStorage.getItem(this.stateStorageKey) || "{}");
        } catch {
            return {};
        }
    }

    saveDashboardState() {
        sessionStorage.setItem(this.stateStorageKey, JSON.stringify({
            period: this.state.period,
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            kpiCustomRanges: this.state.kpiCustomRanges,
            kpiFilters: this.state.kpiFilters,
            revenueChartHidden: this.state.revenueChartHidden,
            partnerSearch: { ...this.state.partnerSearch },
        }));
    }

    scheduleSaveScroll() {
        if (this.scrollSaveTimeout) {
            return;
        }
        this.scrollSaveTimeout = setTimeout(() => {
            this.saveScroll();
            this.scrollSaveTimeout = null;
        }, 150);
    }

    saveScroll() {
        const container = this.scrollContainer || this.getScrollContainer();
        const top = container === window
            ? window.scrollY || document.documentElement.scrollTop || 0
            : container.scrollTop;
        const containerTop = container === window ? 0 : container.getBoundingClientRect().top;
        const anchors = [...(this.boardRef.el?.querySelectorAll("[data-scroll-key]") || [])];
        const anchor = anchors.filter((item) => item.getBoundingClientRect().top <= containerTop + 2).at(-1);
        const anchorTop = anchor ? anchor.getBoundingClientRect().top - containerTop + top : 0;
        const scrollHeight = container === window ? document.documentElement.scrollHeight : container.scrollHeight;
        sessionStorage.setItem(this.scrollStorageKey, JSON.stringify({
            top,
            ratio: scrollHeight > 0 ? top / scrollHeight : 0,
            anchor: anchor?.dataset.scrollKey || null,
            anchorOffset: anchor ? top - anchorTop : 0,
            savedAt: Date.now(),
        }));
    }

    restoreScroll() {
        const storedValue = sessionStorage.getItem(this.scrollStorageKey);
        if (!storedValue) return;
        let savedScroll = 0;
        let savedState = {};
        try {
            const parsed = JSON.parse(storedValue);
            savedState = typeof parsed === "object" && parsed ? parsed : {};
            savedScroll = Number(parsed?.top ?? parsed) || 0;
        } catch {
            savedScroll = Number(storedValue) || 0;
        }
        const container = this.scrollContainer || this.getScrollContainer();
        const applyScroll = () => {
            let target = savedScroll;
            const anchor = savedState.anchor
                ? this.boardRef.el?.querySelector(`[data-scroll-key="${savedState.anchor}"]`)
                : null;
            if (anchor) {
                const currentTop = container === window ? window.scrollY : container.scrollTop;
                const containerTop = container === window ? 0 : container.getBoundingClientRect().top;
                const anchorTop = anchor.getBoundingClientRect().top - containerTop + currentTop;
                target = anchorTop + (Number(savedState.anchorOffset) || 0);
            } else if (savedState.ratio) {
                const height = container === window ? document.documentElement.scrollHeight : container.scrollHeight;
                target = height * savedState.ratio;
            }
            if (container === window) {
                if (Math.abs(window.scrollY - target) > 1) window.scrollTo(0, target);
            } else {
                if (Math.abs(container.scrollTop - target) > 1) container.scrollTop = target;
            }
        };
        requestAnimationFrame(() => {
            applyScroll();
            setTimeout(applyScroll, 80);
            setTimeout(applyScroll, 220);
        });
    }

    getScrollContainer() {
        let element = this.boardRef.el?.parentElement;
        while (element) {
            const style = window.getComputedStyle(element);
            if (/(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight) {
                return element;
            }
            element = element.parentElement;
        }
        return window;
    }

    revenueCurvePoints() {
        const items = this.state.revenue_chart.items || [];
        if (!items.length) return "0,55 100,55";
        const maximum = Math.max(...items.map((item) => Number(item.value) || 0));
        if (!maximum) return "0,55 100,55";
        const last = Math.max(items.length - 1, 1);
        return items.map((item, index) => {
            const ratio = Math.max(0, Math.min((Number(item.value) || 0) / maximum, 1));
            return `${(index / last) * 100},${88 - ratio * 76}`;
        }).join(" ");
    }

    revenueSummary() {
        const values = (this.state.revenue_chart.items || []).map((item) => Number(item.value) || 0);
        const total = values.reduce((sum, value) => sum + value, 0);
        const nonZero = values.filter((value) => value > 0);
        const first = values[0] || 0;
        const last = values[values.length - 1] || 0;
        return { total, max: Math.max(...values, 0), min: nonZero.length ? Math.min(...nonZero) : 0, average: values.length ? total / values.length : 0, trend: first ? ((last - first) / first) * 100 : 0 };
    }

    revenueCurveDots() {
        const items = this.state.revenue_chart.items || [];
        const maximum = Math.max(...items.map((item) => Number(item.value) || 0));
        const last = Math.max(items.length - 1, 1);
        return items.map((item, index) => ({ key: item.key, x: (index / last) * 100, y: maximum ? 88 - ((Number(item.value) || 0) / maximum) * 76 : 55 }));
    }


    revenueCashflowSeries() {
        const items = this.state.revenue_chart.items || [];
        let cumulative = 0;
        return items.map((item, index) => {
            const income = Number(item.income ?? item.incoming ?? item.encaissements ?? item.value) || 0;
            const expense = Number(item.expense ?? item.outgoing ?? item.decaissements) || 0;
            cumulative += income - expense;
            const balance = Number(item.balance ?? item.cumulative ?? item.solde_cumule ?? cumulative) || 0;
            return {
                key: item.key || `${item.label || "point"}-${index}`,
                label: item.label,
                income,
                expense,
                balance,
            };
        });
    }

    revenueChartMaximum() {
        const series = this.revenueCashflowSeries();
        const maximum = Math.max(...series.flatMap((item) => [item.income, item.expense, item.balance]), 0);
        if (!maximum) {
            return 1;
        }
        const magnitude = 10 ** Math.max(Math.floor(Math.log10(maximum)) - 1, 0);
        return Math.ceil(maximum / magnitude) * magnitude;
    }

    revenueSeriesPoints(type) {
        const series = this.revenueCashflowSeries();
        const maximum = this.revenueChartMaximum();
        const last = Math.max(series.length - 1, 1);
        return series.map((item, index) => {
            const value = Math.max(0, Number(item[type]) || 0);
            return {
                key: `${type}-${item.key}`,
                x: (index / last) * 100,
                y: 88 - Math.min(value / maximum, 1) * 80,
            };
        });
    }

    revenueSeriesPath(type) {
        const points = this.revenueSeriesPoints(type);
        if (!points.length) {
            return "M 0 88 L 100 88";
        }
        if (points.length === 1) {
            return `M ${points[0].x} ${points[0].y}`;
        }
        return points.reduce((path, point, index) => {
            if (!index) {
                return `M ${point.x} ${point.y}`;
            }
            const previous = points[index - 1];
            const controlOffset = (point.x - previous.x) * 0.45;
            return `${path} C ${previous.x + controlOffset} ${previous.y}, ${point.x - controlOffset} ${point.y}, ${point.x} ${point.y}`;
        }, "");
    }

    revenueSeriesDots(type) {
        return this.revenueSeriesPoints(type);
    }

    revenueGridLines() {
        const items = this.state.revenue_chart.items || [];
        const last = Math.max(items.length - 1, 1);
        return [0, 1, 2, 3, 4].map((index) => ({
            key: `grid-${index}`,
            y: 8 + index * 20,
            x: items.length ? (index / Math.max(4, last)) * 100 : index * 25,
        }));
    }
    revenueScaleLabels() {
        const maximum = this.revenueChartMaximum();
        return [maximum, maximum * .75, maximum * .5, maximum * .25, 0].map((value, index) => ({ key: `scale-${index}`, label: this.formatCompactAmount(value) }));
    }

    formatCompactAmount(value) {
        return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.round(value || 0));
    }

    formatKpiValue(value, suffix = "") {
        const numericValue = Number(value) || 0;
        const absoluteValue = Math.abs(numericValue);
        const scales = [
            { threshold: 1e12, divisor: 1e12, label: "T" },
            { threshold: 1e9, divisor: 1e9, label: "Md" },
            { threshold: 1e6, divisor: 1e6, label: "M" },
            { threshold: 1e3, divisor: 1e3, label: "K" },
        ];
        const scale = scales.find((item) => absoluteValue >= item.threshold);
        if (!scale) {
            return this.format(numericValue, suffix);
        }
        const scaledValue = numericValue / scale.divisor;
        const scaledAbsoluteValue = Math.abs(scaledValue);
        const maximumFractionDigits = scaledAbsoluteValue < 10 ? 2 : scaledAbsoluteValue < 100 ? 1 : 0;
        const compactValue = new Intl.NumberFormat("fr-FR", {
            minimumFractionDigits: 0,
            maximumFractionDigits,
        }).format(scaledValue);
        return `${compactValue} ${scale.label}${suffix ? ` ${suffix}` : ""}`;
    }

    scheduleKpiValueFit() {
        if (this.kpiFitFrame) cancelAnimationFrame(this.kpiFitFrame);
        this.kpiFitFrame = requestAnimationFrame(() => {
            this.kpiFitFrame = null;
            for (const element of this.boardRef.el?.querySelectorAll(".pt-eb-kpi-value") || []) {
                element.textContent = element.dataset.fullValue || "";
                element.classList.remove("is-compact");
                if (element.scrollWidth > element.clientWidth + 1) {
                    element.textContent = element.dataset.compactValue || element.dataset.fullValue || "";
                    element.classList.add("is-compact");
                }
            }
        });
    }

    categoryColor(index) {
        return ["#2f80ed", "#16a34a", "#fb923c", "#8b5cf6", "#64748b", "#ef4444"][index % 6];
    }

    categoryDonutStyle() {
        const items = this.state.categories?.items || [];
        if (!items.length) return "background: conic-gradient(#e2e8f0 0 100%)";
        const colors = ["#2f80ed", "#16a34a", "#fb923c", "#8b5cf6", "#ef4444", "#64748b"];
        let cursor = 0;
        const segments = items.map((item, index) => {
            const end = Math.min(cursor + (Number(item.percent) || 0), 100);
            const segment = `${colors[index % colors.length]} ${cursor}% ${end}%`;
            cursor = end;
            return segment;
        });
        return `background: conic-gradient(${segments.join(", ")})`;
    }

    toggleRevenueChart() {
        this.state.revenueChartHidden = !this.state.revenueChartHidden;
        this.saveDashboardState();
    }

    openAction(action) {
        if (action) {
            this.saveDashboardState();
            this.saveScroll();
            this.actionService.doAction(action);
        }
    }

    toggleCategoryMenu(ev) {
        ev.stopPropagation();
        this.state.categoryMenuOpen = !this.state.categoryMenuOpen;
    }

    openCategoryAction(action) {
        this.state.categoryMenuOpen = false;
        this.openAction(action);
    }

    async refreshCategoryKpi() {
        this.state.categoryMenuOpen = false;
        await this.loadBoard({ silent: true, force: true });
    }

    userInitials() {
        const name = this.state.current_user?.name || "DG";
        return name.split(" ").filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    }

    todayLabel() {
        return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date());
    }

    timeLabel() {
        return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(this.state.clockTick));
    }

    format(value, suffix = "") {
        const amount = new Intl.NumberFormat("fr-FR").format(Math.round(value || 0));
        return suffix ? `${amount} ${suffix}` : amount;
    }

    formatPercent(value) {
        return `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0)} %`;
    }
}

ExecutiveBoard.template = "primetech_reporting_center.ExecutiveBoard";
