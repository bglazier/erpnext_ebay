# -*- coding: utf-8 -*-

import types

import frappe
from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

from erpnext_ebay.utils.general_utils import divide_rounded


def sales_invoice_before_validate(doc, _method):
    """For eBay SINVs, use the alternative taxes and totals."""
    if doc.is_pos and doc.pos_profile and doc.pos_profile.startswith('eBay'):
        doc.calculate_taxes_and_totals = types.MethodType(
            calculate_taxes_and_totals, doc)


def sales_invoice_before_insert(doc, _method):
    """Remove the ebay_order_id when amending this Sales Invoice"""
    if doc.get("amended_from"):
        doc.ebay_order_id = None

##########################################################
# Override various taxes and totals stuff for eBay SINVs #
##########################################################


class UGSCalculateTaxesAndTotals(calculate_taxes_and_totals):
    """Extended version of calculate_taxes_and_totals that can be patched
    into SINVs for eBay.
    For SINVs only!
    """

    def calculate_outstanding_amount(self):
        super().calculate_outstanding_amount()
        if self.doc.get('is_pos') and self.doc.get('is_return'):
            grand_total = self.doc.rounded_total or self.doc.grand_total
            amount_to_pay = flt(
                grand_total
                - self.doc.total_advance
                - flt(self.doc.write_off_amount),
                self.doc.precision("grand_total")
            )
            self.update_paid_amount_for_return(amount_to_pay)

    def calculate_item_values(self):
        super().calculate_item_values()
        # Share out converted base_amount
        if self.doc.party_account_currency == self.doc.currency:
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


def calculate_taxes_and_totals(self):
    """Replacement for calculate_taxes_and_totals on SINV."""
    from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

    UGSCalculateTaxesAndTotals(self)
    self.calculate_commission()
    self.calculate_contribution()
