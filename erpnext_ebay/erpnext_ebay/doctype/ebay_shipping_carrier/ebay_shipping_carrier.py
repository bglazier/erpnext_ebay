# -*- coding: utf-8 -*-
# Copyright (c) 2021, Ben Glazier and contributors
# For license information, please see license.txt

import datetime
import json

from erpnext_ebay.ebay_constants import (
    EBAY_SITE_IDS, EBAY_TRANSACTION_SITE_IDS)
from erpnext_ebay.ebay_get_requests import get_cached_ebay_details

import frappe
from frappe.model.document import Document


ENTRY_MAPPING = {
    'Description': 'description',
    'ShippingCarrierID': 'shipping_carrier_id',
    'site_codes': 'site_codes'
}

@frappe.whitelist()
def client_sync_shipping_carriers(site_ids=EBAY_SITE_IDS.keys(),
                                  force_update=False):
    """Get ShippingCarrierDetails for these eBay site IDs, and
    update all eBay Shipping Carrier documents.
    All other eBay Shipping Carrier documents are disabled.
    """

    # This is a whitelisted function; check permissions
    if 'System Manager' not in frappe.get_roles(frappe.session.user):
        return frappe.PermissionError(
            'Only System Managers can update the eBay Shipping Carriers.')

    if isinstance(site_ids, str):
        site_ids = json.loads(site_ids)

    sync_shipping_carriers(site_ids, force_update)


def sync_shipping_carriers(site_ids=EBAY_SITE_IDS.keys(), force_update=False):
    """Get ShippingCarrierDetails for these eBay site IDs, and
    update all eBay Shipping Carrier documents.
    All other eBay Shipping Carrier documents are disabled.
    """

    # Add 'GENERIC' entry now, if it does not already exist
    # Not a real shipping carrier, but returned from some eBay sites
    # Disabled so it can't be used for input
    if not frappe.db.exists('eBay Shipping Carrier', 'GENERIC'):
        frappe.get_doc({
            'doctype': 'eBay Shipping Carrier',
            'disabled': True,
            'shipping_carrier': 'GENERIC',
            'description': 'GENERIC',
            'shipping_carrier_id': -1,
            'site_codes': '[]'
        }).insert()

    # Get entries from eBay
    new_entries = {}
    for site_id in site_ids:
        site_code = EBAY_TRANSACTION_SITE_IDS[site_id]
        site_entries = get_cached_ebay_details(
            'ShippingCarrierDetails', site_id=site_id,
            force_update=force_update
        )
        for site_entry in site_entries:
            if site_entry['ShippingCarrier'] in new_entries:
                entry = new_entries[site_entry['ShippingCarrier']]
                # Check values match
                for key in ('Description', 'ShippingCarrierID'):
                    if site_entry[key] != entry[key]:
                        frappe.throw(f'Shipping Carrier value {key} differs '
                                     + 'between site_ids!')
                # Add site code
                entry['site_codes'].append(site_code)
            else:
                # Create new entry
                new_entries[site_entry['ShippingCarrier']] = {
                    'ShippingCarrier': site_entry['ShippingCarrier'],
                    'Description': site_entry['Description'],
                    'ShippingCarrierID': site_entry['ShippingCarrierID'],
                    'site_codes': [site_code]
                }
    for entry in new_entries.values():
        entry['site_codes'] = json.dumps(entry['site_codes'])

    # Get existing entries from database
    current_entries = frappe.get_all(
        'eBay Shipping Carrier',
        fields=[
            'name', 'disabled', 'shipping_carrier', 'description',
            'shipping_carrier_id', 'site_codes'
        ]
    )
    current_entries_dict = {x.shipping_carrier: x for x in current_entries}

    # Loop over new entries and update/insert
    for shipping_carrier, entry in new_entries.items():
        # Test if updating entries, or adding new ones
        if shipping_carrier in current_entries_dict:
            old_entry = current_entries_dict[shipping_carrier]
            # Update existing entry
            for ebay_key, sys_key in ENTRY_MAPPING.items():
                if entry[ebay_key] != getattr(old_entry, sys_key):
                    frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                        sys_key, entry[ebay_key])
            if old_entry.disabled:
                frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                    'disabled', False)
            # Remove old entry from list
            del current_entries_dict[shipping_carrier]
        else:
            # Create new entry
            esc_dict = {
                'doctype': 'eBay Shipping Carrier',
                'shipping_carrier': shipping_carrier,
                'disabled': False,
            }
            for ebay_key, sys_key in ENTRY_MAPPING.items():
                esc_dict[sys_key] = entry[ebay_key]
            frappe.get_doc(esc_dict).insert(ignore_permissions=True)

    # Disable all remaining entries
    for old_entry in current_entries_dict.values():
        if not old_entry.disabled:
            frappe.db.set_value('eBay Shipping Carrier', old_entry.name,
                                'disabled', True)


class eBayShippingCarrier(Document):
    pass
