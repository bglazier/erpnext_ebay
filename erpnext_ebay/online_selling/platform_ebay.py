# -*- coding: utf-8 -*-
"""Code for the eBay platform"""

import frappe

from erpnext_ebay.ebay_constants import EBAY_TRANSACTION_SITE_NAMES
from erpnext_ebay.ebay_requests import get_seller_list, get_item
from erpnext_ebay.sync_listings import (create_ebay_online_selling_item,
                                        OUTPUT_SELECTOR)
from erpnext_ebay.online_selling.platform_base import OnlineSellingPlatformClass


class eBayPlatform(OnlineSellingPlatformClass):
    """This is a class used only to store data and methods in an easy-to-pass
    object. This could just as easily be a dictionary, but there is no
    significant harm to using a class here."""

    delete_entries_on_item_onload = True

    delete_entries_on_item_save = True

    @classmethod
    def item_async_entries(cls, item_code, subtypes):
        """Regenerate all eBay Online Selling items for this item.
        item_onload will have already deleted previous entries.
        """

        entries = []

        site_ids = cls.get_site_ids(subtypes)

        # Get listings from GetSellerList (US site, so we get SiteID)
        get_seller_listings = get_seller_list(
            item_codes=[item_code], site_id=0,
            output_selector=OUTPUT_SELECTOR, granularity_level='Fine',
            days_before=60, days_after=59, active_only=False)

        for listing in get_seller_listings:
            item_site_id = EBAY_TRANSACTION_SITE_NAMES[listing['Site']]

            if item_site_id not in site_ids:
                # We don't handle this site_id
                continue

            new_listing = create_ebay_online_selling_item(
                listing, item_code, site_id=item_site_id)
            if new_listing is not None:
                # Check this was a supported listing type (else None)
                entries.append(new_listing)

        return entries

    @staticmethod
    def get_site_ids(subtypes):
        """Get all eBay site_ids from the Online Selling Subtypes associated
        with the eBay Online Selling Platform."""
        site_ids = set()

        for subtype in subtypes:
            site_ids.add(frappe.get_value(
                'Online Selling Subtype', subtype['name'], 'subtype_id'))

        return site_ids
