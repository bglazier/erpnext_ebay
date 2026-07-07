# -*- coding: utf-8 -*-
# Copyright (c) 2015, Ben Glazier and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class eBaysynclog(Document):

    @staticmethod
    def clear_old_logs(days=120):
        """Allows use in Log Settings for automated log clearing."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        table = frappe.qb.DocType("eBay sync log")
        frappe.db.delete(
            table,
            filters=(table.ebay_sync_datetime < (Now() - Interval(days=days)))
        )
