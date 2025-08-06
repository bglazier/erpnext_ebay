# -*- coding: utf-8 -*-

"""Scheduled tasks to be run by erpnext_ebay"""

import datetime

import frappe
from frappe.utils.background_jobs import enqueue


def all():
    pass


def hourly():
    pass


def daily():
    if not frappe.db.get_single_value('eBay Manager Settings', 'enable_ebay'):
        return
    enqueue('erpnext_ebay.ebay_categories.category_sync',
            queue='long', job_name='eBay Category Sync')
    enqueue('erpnext_ebay.erpnext_ebay.doctype.ebay_shipping_carrier.'
            + 'ebay_shipping_carrier.sync_shipping_carriers',
            queue='long', job_name='eBay Shipping Carrier Sync')
    enqueue('erpnext_ebay.tasks.clear_old_ebay_sync_logs',
            queue='long', job_name='Clear old eBay sync logs')


def weekly():
    pass


def monthly():
    pass


def clear_old_ebay_sync_logs():
    """Delete any eBay sync logs older than 120 days."""

    DAYS = 120

    today = frappe.utils.getdate()

    cut_off_date = today - datetime.timedelta(days=DAYS)

    frappe.db.sql("""
        DELETE LOW_PRIORITY QUICK
        FROM `tabeBay sync log`
        WHERE creation < %(cut_off_date)s;
    """, {'cut_off_date': cut_off_date})
