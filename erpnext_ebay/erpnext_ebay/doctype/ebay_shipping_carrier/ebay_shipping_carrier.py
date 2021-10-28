# -*- coding: utf-8 -*-
# Copyright (c) 2021, Ben Glazier and contributors
# For license information, please see license.txt

import datetime

from erpnext_ebay.ebay_constants import (
    HOME_SITE_ID, EBAY_TRANSACTION_SITE_IDS)
from erpnext_ebay.ebay_get_requests import get_cached_ebay_details

import frappe
from frappe.model.document import Document


ENTRY_MAPPING = {
    'Description': 'description',
    'ShippingCarrierID': 'shipping_carrier_id',
    'detail_version': 'detail_version',
    'update_time': 'update_time'
}


@frappe.whitelist()
def client_sync_shipping_carriers(site_id=HOME_SITE_ID):
    """Get ShippingCarrierDetails for this eBay site ID, and
    update all eBay Shipping Carrier documents for this site_id."""

    # This is a whitelisted function; check permissions
    if 'System Manager' not in frappe.get_roles(frappe.session.user):
        return frappe.PermissionError(
            'Only System Managers can update the eBay Shipping Carriers.')

    if isinstance(site_id, str):
        site_id = int(site_id)

    sync_shipping_carriers(site_id)


def sync_shipping_carriers(site_id=HOME_SITE_ID):
    """Get ShippingCarrierDetails for this eBay site ID, and
    update all eBay Shipping Carrier documents for this site_id.
    """
    site_code = EBAY_TRANSACTION_SITE_IDS[site_id]

    current_entries = frappe.get_all(
        'eBay Shipping Carrier',
        fields=[
            'name', 'disabled', 'shipping_carrier', 'description',
            'shipping_carrier_id', 'detail_version', 'update_time'
        ],
        filters={'site_code': site_code}
    )
    new_entries = get_cached_ebay_details(
        'ShippingCarrierDetails', site_id=site_id, force_update=True
    )
    current_entries_dict = {x.shipping_carrier: x for x in current_entries}

    # Loop over new entries and update/insert
    for entry in new_entries:
        # Process values into correct types
        entry['update_time'] = frappe.utils.convert_utc_to_user_timezone(
            datetime.datetime.fromisoformat(entry['UpdateTime'][:-1])
        ).replace(tzinfo=None)
        entry['detail_version'] = int(entry['DetailVersion'])
        # Test if updating entries, or adding new ones
        if entry['ShippingCarrier'] in current_entries_dict:
            old_entry = current_entries_dict[entry['ShippingCarrier']]
            # Update existing entry
            for ebay_key, sys_key in ENTRY_MAPPING.items():
                if entry[ebay_key] != getattr(old_entry, sys_key):
                    frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                        sys_key, entry[ebay_key])
            if old_entry.disabled:
                frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                    'disabled', False)
            # Remove old entry from list
            del current_entries_dict[entry['ShippingCarrier']]
        else:
            # Create new entry
            esc_dict = {
                'doctype': 'eBay Shipping Carrier',
                'shipping_carrier': entry['ShippingCarrier'],
                'disabled': False,
                'site_code': site_code
            }
            for ebay_key, sys_key in ENTRY_MAPPING.items():
                esc_dict[sys_key] = entry[ebay_key]
            frappe.get_doc(esc_dict).insert()

    # Disable all remaining entries
    for old_entry in current_entries_dict.values():
        if not old_entry.disabled:
            frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                'disabled', True)


class eBayShippingCarrier(Document):
    pass
