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


@frappe.whitelist()
def view_slideshow_py(slideshow):
    """Return a list of images from a Website Slideshow"""

    # Whitelisted function; check permissions
    if not frappe.has_permission('Item', 'read'):
        frappe.throw('Need read permissions on Item!',
                     frappe.PermissionError)

    image_dicts = frappe.get_all(
        'Website Slideshow Item',
        fields=['image'],
        filters={'parent': slideshow},
        order_by='idx')

    return [x.image for x in image_dicts]
