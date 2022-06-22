# -*- coding: utf-8 -*-

import types

import frappe


def sales_invoice_before_validate(doc, _method):
    """For eBay SINVs, use the alternative taxes and totals."""
    # Don't use rounded total because it is broken in ERPNext...
    doc.disable_rounded_total = True


def sales_invoice_before_insert(doc, _method):
    """Remove the ebay_order_id when amending this Sales Invoice"""
    if doc.get("amended_from"):
        doc.ebay_order_id = None
