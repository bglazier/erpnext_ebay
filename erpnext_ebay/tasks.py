# -*- coding: utf-8 -*-

"""Scheduled tasks to be run by erpnext_ebay"""

from frappe.utils.background_jobs import enqueue


def all():
    pass


def hourly():
    enqueue('erpnext_ebay.sync_orders.sync',
            queue='long', job_name='Sync eBay Orders')


def daily():
    enqueue('erpnext_ebay.ebay_active_listings.update_ebay_data',
            queue='long', job_name='Update eBay Data',
            multiple_error_sites=['UK'])
    enqueue('erpnext_ebay.ebay_categories.category_sync',
            queue='long', job_name='eBay Category Sync')


def weekly():
    pass


def monthly():
    pass
