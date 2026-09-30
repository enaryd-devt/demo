<<<<<<< HEAD
from odoo import models
from .income_statement_mapping import INCOME_STATEMENT_STRUCTURE

class IncomeStatement(models.AbstractModel):
    _name = 'primetech.income.statement'
    _description = 'Compte de Résultat OHADA'

    def _compute_amount(self, accounts, date_from, date_to, posted_only=True):
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if posted_only:
            domain.append(('move_id.state', '=', 'posted'))
        move_lines = self.env['account.move.line'].search(domain)
        amount = 0.0
        for line in move_lines:
            account_code = line.account_id.code or ''
            if any((account_code.startswith(prefix) for prefix in accounts)):
                amount += line.credit - line.debit
        return amount

    def get_income_statement(self, date_from, date_to, posted_only=True):
        date_from_n1 = date_from.replace(year=date_from.year - 1)
        date_to_n1 = date_to.replace(year=date_to.year - 1)
        values_n = {}
        values_n1 = {}
        for item in INCOME_STATEMENT_STRUCTURE:
            if item['type'] != 'line':
                continue
            amount_n = self._compute_amount(item['accounts'], date_from, date_to, posted_only)
            amount_n1 = self._compute_amount(item['accounts'], date_from_n1, date_to_n1, posted_only)
            if item['sign'] == '-':
                amount_n *= -1
                amount_n1 *= -1
            values_n[item['ref']] = amount_n
            values_n1[item['ref']] = amount_n1
        values_n['XA'] = values_n.get('TA', 0.0) - values_n.get('RA', 0.0) - values_n.get('RB', 0.0)
        values_n1['XA'] = values_n1.get('TA', 0.0) - values_n1.get('RA', 0.0) - values_n1.get('RB', 0.0)
        values_n['XB'] = values_n.get('TB', 0.0) + values_n.get('TC', 0.0) + values_n.get('TD', 0.0)
        values_n1['XB'] = values_n1.get('TB', 0.0) + values_n1.get('TC', 0.0) + values_n1.get('TD', 0.0)
        values_n['XC'] = values_n['XA'] + values_n['XB'] + values_n.get('TE', 0.0) + values_n.get('TF', 0.0) + values_n.get('TG', 0.0) + values_n.get('TH', 0.0) + values_n.get('TI', 0.0) - values_n.get('RC', 0.0) - values_n.get('RD', 0.0) - values_n.get('RE', 0.0) - values_n.get('RF', 0.0) - values_n.get('RG', 0.0) - values_n.get('RH', 0.0) - values_n.get('RI', 0.0) - values_n.get('RJ', 0.0)
        values_n1['XC'] = values_n1['XA'] + values_n1['XB'] + values_n1.get('TE', 0.0) + values_n1.get('TF', 0.0) + values_n1.get('TG', 0.0) + values_n1.get('TH', 0.0) + values_n1.get('TI', 0.0) - values_n1.get('RC', 0.0) - values_n1.get('RD', 0.0) - values_n1.get('RE', 0.0) - values_n1.get('RF', 0.0) - values_n1.get('RG', 0.0) - values_n1.get('RH', 0.0) - values_n1.get('RI', 0.0) - values_n1.get('RJ', 0.0)
        values_n['XD'] = values_n['XC'] - values_n.get('RK', 0.0)
        values_n1['XD'] = values_n1['XC'] - values_n1.get('RK', 0.0)
        values_n['XE'] = values_n['XD'] - values_n.get('RL', 0.0)
        values_n1['XE'] = values_n1['XD'] - values_n1.get('RL', 0.0)
        values_n['XF'] = values_n.get('TK', 0.0) - values_n.get('RN', 0.0)
        values_n1['XF'] = values_n1.get('TK', 0.0) - values_n1.get('RN', 0.0)
        values_n['XH'] = values_n.get('TN', 0.0) - values_n.get('RP', 0.0)
        values_n1['XH'] = values_n1.get('TN', 0.0) - values_n1.get('RP', 0.0)
        values_n['XI'] = values_n['XE'] + values_n['XF'] + values_n['XH'] - values_n.get('RQ', 0.0) - values_n.get('RS', 0.0)
        values_n1['XI'] = values_n1['XE'] + values_n1['XF'] + values_n1['XH'] - values_n1.get('RQ', 0.0) - values_n1.get('RS', 0.0)
        lines = []
        for item in INCOME_STATEMENT_STRUCTURE:
            ref = item['ref']
            if item['type'] == 'line':
                lines.append({'ref': ref, 'label': item['label'], 'sign': item.get('sign', ''), 'note': item.get('note', ''), 'amount': values_n.get(ref, 0.0), 'amount_n1': values_n1.get(ref, 0.0), 'line_type': 'subtotal'})
            else:
                lines.append({'ref': ref, 'label': item['label'], 'sign': '', 'note': '', 'amount': values_n.get(ref, 0.0), 'amount_n1': values_n1.get(ref, 0.0), 'line_type': 'subtotal'})
        return {'lines': lines, 'year_n': date_to.year, 'year_n1': date_to.year - 1, 'resultat_net': values_n.get('XI', 0.0)}
=======
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import fields, models

from .income_statement_mapping import INCOME_STATEMENT_STRUCTURE


class IncomeStatement(models.AbstractModel):
    _name = "primetech.income.statement"
    _description = "Compte de Résultat OHADA"

    def _get_balances_by_code(self, date_from, date_to, posted_only=True):
        """Return signed balances (credit - debit) indexed by account code.

        One grouped query is used for a period. This replaces the former
        implementation which loaded the complete general ledger for every
        single line of the income statement.
        """
        domain = [
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", self.env.company.id),
        ]
        if posted_only:
            domain.append(("move_id.state", "=", "posted"))

        account_model = self.env["account.account"]
        income_expense_accounts = account_model.search([
            "|", "|",
            ("code", "=like", "6%"),
            ("code", "=like", "7%"),
            ("code", "=like", "8%"),
        ])
        if not income_expense_accounts:
            return {}

        account_codes = {
            account.id: account.code or ""
            for account in income_expense_accounts
        }
        grouped_lines = self.env["account.move.line"].read_group(
            domain + [("account_id", "in", income_expense_accounts.ids)],
            ["debit:sum", "credit:sum"],
            ["account_id"],
            lazy=False,
        )

        balances = defaultdict(float)
        for group in grouped_lines:
            account = group.get("account_id")
            account_id = account and account[0]
            code = account_codes.get(account_id)
            if code:
                balances[code] += (group.get("credit") or 0.0) - (group.get("debit") or 0.0)
        return balances

    @staticmethod
    def _amount_for_item(item, balances):
        account_prefixes = item.get("accounts", ())
        excluded_prefixes = item.get("exclude_accounts", ())
        return sum(
            amount
            for code, amount in balances.items()
            if any(code.startswith(prefix) for prefix in account_prefixes)
            and not any(code.startswith(prefix) for prefix in excluded_prefixes)
        )

    def _get_period_values(self, date_from, date_to, posted_only):
        balances = self._get_balances_by_code(date_from, date_to, posted_only)
        values = {}
        for item in INCOME_STATEMENT_STRUCTURE:
            if item["type"] == "line":
                values[item["ref"]] = self._amount_for_item(item, balances)
            else:
                values[item["ref"]] = sum(
                    values.get(reference, 0.0)
                    for reference in item["formula"]
                )
        return values

    def get_income_statement(self, date_from, date_to, posted_only=True):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            return {"lines": [], "resultat_net": 0.0}

        previous_date_from = date_from - relativedelta(years=1)
        previous_date_to = date_to - relativedelta(years=1)
        values_n = self._get_period_values(date_from, date_to, posted_only)
        values_n1 = self._get_period_values(
            previous_date_from,
            previous_date_to,
            posted_only,
        )

        lines = []
        for item in INCOME_STATEMENT_STRUCTURE:
            reference = item["ref"]
            lines.append({
                "ref": reference,
                "label": item["label"],
                "marker": item.get("marker", ""),
                "sign": item.get("sign", ""),
                "note": item.get("note", ""),
                "amount": values_n.get(reference, 0.0),
                "amount_n1": values_n1.get(reference, 0.0),
                "line_type": item["type"],
            })

        return {
            "lines": lines,
            "year_n": date_to.year,
            "year_n1": previous_date_to.year,
            "date_from": date_from,
            "date_to": date_to,
            "company": self.env.company,
            "resultat_net": values_n.get("XI", 0.0),
        }
>>>>>>> cf63a5b (update)
