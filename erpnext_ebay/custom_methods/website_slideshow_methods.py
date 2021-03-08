# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""

import frappe


def website_slideshow_validate(doc, _method):
    """On Website Slideshow validate docevent."""

    if doc.number_of_ebay_images > 12:
        frappe.throw('Number of eBay images must be 12 or fewer!')
    if doc.number_of_ebay_images < 1:
        frappe.throw('Number of eBay images must be 1 or greater!')
