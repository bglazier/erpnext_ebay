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

        parent = frappe.qb.DocType("eBay sync log")
        child = frappe.qb.DocType("eBay sync log entry")

        cut_off = Now() - Interval(days=days)

        # Names of the parent logs due to be removed.
        old_logs = (
            frappe.qb.from_(parent)
            .select(parent.name)
            .where(parent.ebay_sync_datetime < cut_off)
        )

        # Delete the child rows first so they are not orphaned; the parent
        # rows still exist at this point, so the subquery can identify them.
        frappe.db.delete(
            child,
            filters=(
                (child.parenttype == "eBay sync log")
                & (child.parent.isin(old_logs))
            )
        )

        # Then delete the parent logs themselves.
        frappe.db.delete(
            parent,
            filters=(parent.ebay_sync_datetime < cut_off)
        )
