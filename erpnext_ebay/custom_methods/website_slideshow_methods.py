# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""

import frappe

MAX_EBAY_IMAGES = 12


def website_slideshow_validate(doc, _method):
    """On Website Slideshow validate docevent."""

    if doc.number_of_ebay_images > MAX_EBAY_IMAGES:
        frappe.throw(
            f'Number of eBay images must be {MAX_EBAY_IMAGES} or fewer!')
    if doc.number_of_ebay_images < 1:
        frappe.throw('Number of eBay images must be 1 or greater!')
