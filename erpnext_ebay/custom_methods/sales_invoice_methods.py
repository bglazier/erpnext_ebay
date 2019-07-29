# -*- coding: utf-8 -*-

import frappe


def sales_invoice_before_insert(self, method):
    """Remove the ebay_order_id when amending this Sales Invoice"""
    if self.get("amended_from"):
        self.ebay_order_id = None
