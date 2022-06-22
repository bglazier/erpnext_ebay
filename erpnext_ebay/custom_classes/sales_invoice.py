# -*- coding: utf-8 -*-
"""A drop-in replacement for Sales Invoice."""

from frappe.utils import flt

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

from erpnext_ebay.utils.general_utils import divide_rounded


class eBaySalesInvoice(SalesInvoice):
    """An extended version of Sales Invoice."""

    def validate_party_account_currency(self):
        """We just don't do this validation for eBay invoices."""
        if self.is_pos and self.pos_profile and self.pos_profile.startswith('eBay'):
            pass
        else:
            super().validate_party_account_currency()

    def calculate_taxes_and_totals(self):
        """For eBay SINVs, use custom logic."""
        if self.is_pos and self.pos_profile and self.pos_profile.startswith('eBay'):
            CustomCalculateTaxesAndTotals(self)
        else:
            calculate_taxes_and_totals(self)

        self.calculate_commission()
        self.calculate_contribution()


##########################################################
# Override various taxes and totals stuff for eBay SINVs #
##########################################################


class CustomCalculateTaxesAndTotals(calculate_taxes_and_totals):
    """Extended version of calculate_taxes_and_totals that can be patched
    into SINVs for eBay.
    For SINVs only!
    """

    def calculate(self):
        party_account_currency = self.doc.party_account_currency
        self.doc.party_account_currency = self.doc.currency
        super().calculate()
        self.doc.party_account_currency = party_account_currency

    def _calculate(self):
        self.calculate_paid_amount()
        super()._calculate()

    def calculate_item_values(self):
        super().calculate_item_values()
        # Share out converted base_amount
        if self.doc.conversion_rate == 1.0:
            return
        if self.doc.get('is_consolidated') or self.discount_amount_applied:
            return
        items = self.doc.get('items')
        amount_total = sum(x.amount for x in items)
        if not amount_total:
            return
        base_amount_total = flt(
            self.doc.conversion_rate * amount_total,
            self.doc.precision('base_total')
        )
        if base_amount_total == sum(x.base_amount for x in items):
            # Sum of item base_amounts equals converted sum of amounts
            return
        # Fudge base_amounts so they add up properly
        base_amount_dict = divide_rounded(
            {x: x.amount for x in items}, base_amount_total
        )
        for item, base_amount in base_amount_dict.items():
            item.base_amount = flt(base_amount, item.precision('base_amount'))
            if not item.qty and self.doc.get('is_return'):
                item.base_rate = flt(-item.base_amount, item.precision('base_rate'))
            elif not item.qty and self.doc.get('is_debit_note'):
                item.base_rate = flt(item.base_amount, item.precision('base_rate'))
            else:
                item.base_rate = flt(item.base_amount / item.qty, item.precision('base_rate'))
            item.base_net_rate = item.base_rate
            item.base_net_amount = item.base_amount
