# -*- coding: utf-8 -*-

import frappe
from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals


def sales_invoice_before_insert(self, method):
    """Remove the ebay_order_id when amending this Sales Invoice"""
    if self.get("amended_from"):
        self.ebay_order_id = None

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

    def calculate_net_total(self):
        super().calculate_net_total()

        if self.doc.party_account_currency != self.doc.currency:
            self.doc.base_total = flt(self.doc.total * self.doc.conversion_rate)
            self.doc.base_net_total = flt(self.doc.net_total * self.doc.conversion_rate)

        self.doc.round_floats_in(self.doc, ["base_total", "base_net_total"])


def calculate_taxes_and_totals(self):
    """Replacement for calculate_taxes_and_totals on SINV."""
    from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

    UGSCalculateTaxesAndTotals(self)
    self.calculate_commission()
    self.calculate_contribution()
