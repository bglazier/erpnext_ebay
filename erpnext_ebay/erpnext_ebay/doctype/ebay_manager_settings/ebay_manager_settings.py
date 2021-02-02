# -*- coding: utf-8 -*-
# Copyright (c) 2015, Ben Glazier and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class eBayHostnameError(frappe.ValidationError):
    pass


@frappe.whitelist()
def get_current_hostname():
    """Get the current hostname of the server."""

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager Settings', 'write'):
        frappe.throw('Need write permissions on eBay Manager Settings!',
                     frappe.PermissionError)

    return frappe.utils.get_url()


def use_sandbox():
    """Determine if the eBay sandbox, rather than the live Trading API,
    should be used.
    The sandbox should be used if ebay_use_sandbox is selected.
    However, if this is not selected and the current hostname is not
    as specified in ebay_live_hostname, then raise an error.
    """
    ebay_use_sandbox = frappe.db.get_single_value(
        'eBay Manager Settings', 'ebay_use_sandbox')
    if ebay_use_sandbox:
        return True
    # Check use of live API is valid
    ebay_live_hostname = frappe.db.get_single_value(
        'eBay Manager Settings', 'ebay_live_hostname')
    if not ebay_live_hostname:
        frappe.throw('Must set eBay live hostname if not using sandbox!',
                     exc=eBayHostnameError)
    hostname = frappe.utils.get_url().strip()
    ebay_hostname = ebay_live_hostname.strip()
    if ebay_hostname != hostname:
        frappe.throw(f'Current hostname {hostname} does not match '
                     + f'eBay live hostname {ebay_hostname}!',
                     exc=eBayHostnameError)
    # OK to use live API (not sandbox)
    return False


class eBayManagerSettings(Document):
    pass
