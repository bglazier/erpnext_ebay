# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""
from __future__ import unicode_literals


import frappe

def item_onload(doc, _method):
    """On item load docevent."""
    item_onload_ebay(doc)

# ********************************************************************
# eBay update for Online Selling Item
# ********************************************************************


def item_onload_ebay(doc):
    """Get the latest active listings for this item."""
    item_code = doc.item_code
    
