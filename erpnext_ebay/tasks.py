# -*- coding: utf-8 -*-

"""Scheduled tasks to be run by erpnext_ebay"""

from frappe.utils.background_jobs import enqueue


def all():
    pass


def hourly():
    pass


def daily():
    enqueue('erpnext_ebay.ebay_categories.category_sync',
            queue='long', job_name='eBay Category Sync')


def weekly():
    pass


def monthly():
    pass
