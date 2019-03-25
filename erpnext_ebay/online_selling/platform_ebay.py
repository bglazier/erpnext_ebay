# -*- coding: utf-8 -*-
"""Code for the eBay platform"""
from __future__ import unicode_literals

import frappe

from erpnext_ebay.ebay_requests import get_seller_list, get_item
from erpnext_ebay.sync_listings import create_ebay_online_selling_item
from erpnext_ebay.online_selling.platform_base import OnlineSellingPlatformClass


class eBayPlatform(OnlineSellingPlatformClass):
    """This is a class used only to store data and methods in an easy-to-pass
    object. This could just as easily be a dictionary, but there is no
    significant harm to using a class here."""

    delete_entries_on_item_onload = True

    @classmethod
    def item_onload(cls, doc, subtypes):
        """Regenerate all eBay Online Selling items for this item.
        item_onload will have already deleted previous entries.
        """
        item_code = doc.item_code

        site_ids = cls.get_site_ids(subtypes)

        for site_id in site_ids:
            # Loop over all installed eBay global sites

            # Get list of ItemIDs from GetSellerList (should really be only one!)
            get_seller_listings = get_seller_list([item_code], site_id)

            item_ids = [x['ItemID'] for x in get_seller_listings]

            # Should really be only one listing per item, but support it
            # anyway...
            for item_id in item_ids:
                item_dict = get_item(item_id=item_id, site_id=site_id)
                new_listing = create_ebay_online_selling_item(
                    item_dict, item_code, site_id=site_id)
                if new_listing is not None:
                    # Check this was a supported listing type (else None)
                    new_listing.insert(ignore_permissions=True)
                    doc.online_selling_items.append(new_listing)

    @classmethod
    def item_update(cls, doc, subtype, update_dict):
        """We have a number of updates. Revise our item appropriately."""
        if 'standard_rate' in update_dict:
            # update standard price
            pass

    @staticmethod
    def get_site_ids(subtypes):
        """Get all eBay site_ids from the Online Selling Subtypes associated
        with the eBay Online Selling Platform."""
        site_ids = set()

        for subtype in subtypes:
            site_ids.add(frappe.get_value(
                'Online Selling Subtype', subtype['name'], 'subtype_id'))

        return site_ids
