# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import sys
import datetime
import traceback
from types import MethodType

import six
import frappe
from frappe import msgprint, _
from frappe.utils import cstr, strip_html

from ebay_requests import get_orders, default_site_id
from ebay_constants import EBAY_TRANSACTION_SITE_IDS

# Option to use eBay shipping address name as customer name.
# eBay does not normally provide buyer name.
assume_shipping_name_is_ebay_name = True

# Should we print debugging messages?
msgprint_debug = False

# Should we log changes?
use_sync_log = True

# Continue on errors:
continue_on_error = True

# Maximum number of attempts to add duplicate address (by adding -1, -2 etc)
maximum_address_duplicates = 4

# EU countries
EU_COUNTRIES = ['austria', 'belgium', 'bulgaria', 'croatia', 'cyprus',
                'czech republic', 'denmark', 'estonia', 'finland', 'france',
                'germany', 'greece', 'hungary', 'ireland', 'italy', 'latvia',
                'lithuania', 'luxembourg', 'malta', 'netherlands', 'poland',
                'portugal', 'romania', 'slovakia', 'slovenia', 'spain',
                'sweden', 'united kingdom']

EBAY_ID_NAMES = {'Customer': 'ebay_user_id',
                 'Address': 'ebay_address_id',
                 'eBay order': 'ebay_order_id',
                 'Sales Invoice': 'ebay_order_id'}

VAT_RATES = {'Sales - URTL': 0.2,
             'Sales Non EU - URTL': 0.0}
VAT_PERCENT = {k: 100*v for k, v in VAT_RATES.items()}

SHIPPING_ITEM = 'ITEM-00358'


class ErpnextEbaySyncError(Exception):
    pass


def debug_msgprint(message):
    """Simple wrapper for msgprint that also prints to the console.

    Doesn't msgprint if msgprint_debug is not true.
    """
    if six.PY2:
        print(message.encode('ascii', errors='xmlcharrefreplace'))
    else:
        print(message)
    if msgprint_debug:
        msgprint(message)


@frappe.whitelist()
def sync(site_id=None):
    """
    Pulls the latest orders from eBay. Creates Sales Invoices for sold items.
    By default (site_id = None or -1), checks orders from all eBay sites.
    If site_id is specified, only orders from that site are used.

    We loop over each order in turn. First we extract customer
    details from eBay. If the customer does not exist, we then create
    a Customer. We update the Customer if it already exists.
    We create an Address for this customer, if one does not already exist,
    and link it to the Customer.

    Then we extract the order information from eBay, and create an
    eBay Order if it does not already exist.

    Finally we create or update a Sales Invoice based on the eBay
    transaction. This is only created if the order is completed (i.e. paid).

    If we raise an ErpnextEbaySyncError during processing of an
    order, then we rollback the database and continue to the next
    order. If a more serious exception occurs, then we rollback the
    database but we only continue if continue_on_error is true.
    """

    if site_id is None or int(site_id) == -1:
        ebay_site_id = None
    else:
        site_id = int(site_id)
        ebay_site_id = EBAY_TRANSACTION_SITE_IDS[site_id]

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay orders...')
    # Load orders from Ebay
    orders, num_days = get_orders()

    # Create a synchronization log
    log_dict = {"doctype": "eBay sync log",
                "ebay_sync_datetime": datetime.datetime.now(),
                "ebay_sync_days": num_days,
                "ebay_log_table": []}
    changes = []
    msgprint_log = []

    try:
        for order in orders:
            try:
                # Check if this is on the correct eBay site.
                site_id_order = order[
                    'TransactionArray']['Transaction'][0]['TransactionSiteID']
                if (ebay_site_id is not None
                        and site_id_order != ebay_site_id):
                    # Not from this site_id - skip
                    continue

                # Create/update Customer
                cust_details, address_details = extract_customer(order)
                create_customer(cust_details, address_details, changes)

                # Create/update eBay Order
                order_details = extract_order_info(order, changes)
                create_ebay_order(order_details, changes, order)

                # Create/update Sales Invoice
                create_sales_invoice(order_details, order, changes)
            except ErpnextEbaySyncError as e:
                # Continue to next order
                frappe.db.rollback()
                msgprint_log.append(str(e))
                print(e)
            except Exception as e:
                # Continue to next order
                frappe.db.rollback()
                err_msg = traceback.format_exc()
                print(err_msg)
                if not continue_on_error:
                    msgprint('ORDER FAILED')
                    raise
                else:
                    msgprint_log.append('ORDER FAILED:\n{}'.format(err_msg))

    finally:
        # Save the log, regardless of how far we got
        frappe.db.commit()
        for change in changes:
            log_dict['ebay_log_table'].append(change)
        log = frappe.get_doc(log_dict)
        if use_sync_log:
            log.insert()
        else:
            del log
        frappe.db.commit()
    msgprint_log.append('Finished.')
    msgprint(msgprint_log)


def extract_customer(order):
    """Process an order, and extract limited customer information.

    order - a single order entry from the eBay TradingAPI.

    Returns a tuple of two dictionarys.
    The first dictionary is ready to create a Customer Doctype entry.
    The second dictionary is ready to create an Address Doctype entry.
    The second dictionary could be replaced by None if there is no address.
    """

    ebay_user_id = order['BuyerUserID']

    is_pickup_order = 'PickupMethodSelected' in order

    shipping_name = order['ShippingAddress']['Name'] or ''
    address_line1 = order['ShippingAddress']['Street1']
    address_line2 = order['ShippingAddress']['Street2']
    city = order['ShippingAddress']['CityName']
    state = order['ShippingAddress']['StateOrProvince']
    postcode = order['ShippingAddress']['PostalCode']
    country = order['ShippingAddress']['CountryName']

    # Tidy up ShippingAddress name, if entirely lower/upper case and not
    # a single word
    if ((shipping_name.islower() or shipping_name.isupper()) and
            ' ' in shipping_name):
        shipping_name = shipping_name.title()

    has_shipping_address = (shipping_name or address_line1 or address_line2
                            or city or state or postcode or country)

    if has_shipping_address and assume_shipping_name_is_ebay_name:
        customer_name = shipping_name or ebay_user_id
    else:
        customer_name = ebay_user_id

    customer_dict = {
        "doctype": "Customer",
        "customer_name": customer_name,
        "ebay_user_id": ebay_user_id,
        "customer_group": _("Individual"),
        "territory": _("All Territories"),
        "customer_type": _("Individual")}

    if has_shipping_address:
        # Attempt to get email address
        transactions = order['TransactionArray']['Transaction']

        email_id = None
        email_ids = [x['Buyer']['Email'] for x in transactions]
        if email_ids.count(email_ids[0]) == len(email_ids):
            # All email_ids are identical
            if email_ids[0] != 'Invalid Request':
                email_id = email_ids[0]

        # Rest of the information
        if not address_line1 and address_line2:
            # If first address line is empty, but the second is not,
            # bump into the first address line (which must not be empty)
            address_line1, address_line2 = address_line2, ''

        if country is not None:
            country = country.title()

            if country in ['UK', 'GB', 'Great Britain']:
                country = 'United Kingdom'

            country_query = frappe.db.get_value(
                'Country', filters={'name': country}, fieldname='name')
            if country_query is None:
                if address_line2:
                    address_line2 = address_line2 + '\n' + country
                else:
                    address_line2 = country
                country = None

        # If we have a pickup order, there is no eBay AddressID (so make one)
        if is_pickup_order:
            ebay_address_id = (ebay_user_id + '_PICKUP_' +
                               address_line1.replace(' ', '_'))
        else:
            ebay_address_id = order['ShippingAddress']['AddressID']

        # Prepare the address dictionary
        if postcode is not None and country == 'United Kingdom':
            postcode = sanitize_postcode(postcode)
        address_dict = {
            "doctype": "Address",
            "address_title": shipping_name or ebay_user_id,
            "ebay_address_id": ebay_address_id,
            "address_type": _("Shipping"),
            "address_line1": address_line1 or '-',
            "address_line2": address_line2,
            "city": city or '-',
            "state": state,
            "pincode": postcode,
            "country": country,
            "phone": order['ShippingAddress']['Phone'],
            "email_id": email_id}
    else:
        address_dict = None

    return customer_dict, address_dict


def extract_order_info(order, changes=None):
    """Process an order, and extract limited transaction information.
    order - a single order entry from the eBay TradingAPI.
    changes - A sync log list to append to.
    Returns dictionary for eBay order entries."""

    if changes is None:
        changes = []

    ebay_user_id = order['BuyerUserID']

    # Get customer information
    cust_fields = db_get_ebay_doc(
        "Customer", ebay_user_id, fields=["name", "customer_name"],
        log=changes, none_ok=False)

    # Get address information, if available
    if ('AddressID' in order['ShippingAddress']
            and order['ShippingAddress']['AddressID'] is not None):
        ebay_address_id = order['ShippingAddress']['AddressID']
        country = order['ShippingAddress']['Country']

        db_address_name = db_get_ebay_doc(
            "Address", ebay_address_id, fields=["name"],
            log=changes, none_ok=False)["name"]
    else:
        country = "United Kingdom"
        ebay_address_id = None
        db_address_name = None

    # Return dict of order information, ready for creating an eBay Order
    order_dict = {"doctype": "eBay order",
                  "name": order['OrderID'],
                  "ebay_order_id": order['OrderID'],
                  "ebay_user_id": order['BuyerUserID'],
                  "ebay_address_id": ebay_address_id,
                  "customer": cust_fields["name"],
                  "customer_name": cust_fields["customer_name"],
                  "address": db_address_name,
                  "country": country}

    return order_dict


def create_customer(customer_dict, address_dict, changes=None):
    """Process an order and add the customer; add customer address.
    Does not duplicate entries where possible.

    customer_dict - A dictionary ready to create a Customer doctype.
    address_dict - A dictionary ready to create an Address doctype (or None).
    changes - A sync log list to append to.

    Returns a list of dictionaries for eBay sync log entries.
    """

    if changes is None:
        changes = []

    updated_db = False

    # Test if the customer already exists
    db_cust_name = None
    ebay_user_id = customer_dict['ebay_user_id']
    if address_dict is not None:
        ebay_address_id = address_dict['ebay_address_id']

    cust_fields = db_get_ebay_doc(
        "Customer", ebay_user_id, fields=["name", "customer_name"],
        log=changes, none_ok=True)

    if cust_fields is None:
        # We don't have a customer with a matching ebay_user_id
        # Add the customer
        cust_doc = frappe.get_doc(customer_dict)
        cust_doc.insert()
        db_cust_name = cust_doc.name
        updated_db = True
        debug_msgprint('Adding a user: ' + ebay_user_id +
                       ' : ' + customer_dict['customer_name'])
        changes.append({"ebay_change": "Adding a user",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": customer_dict['customer_name'],
                        "customer": None,
                        "address": None,
                        "ebay_order": None})
    else:
        # We have a customer with a matching ebay_user_id
        db_cust_name = cust_fields['name']
        db_cust_customer_name = cust_fields['customer_name']
        debug_msgprint('User already exists: ' + ebay_user_id +
                       ' : ' + db_cust_customer_name)
        changes.append({"ebay_change": "User already exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": db_cust_customer_name,
                        "customer": db_cust_name,
                        "address": None,
                        "ebay_order": None})

    if address_dict is None:
        # We have not got an address to add
        add_address = False
    else:
        # We have an address which we may need to add
        address_fields = db_get_ebay_doc(
            "Address", ebay_address_id, fields=["name"],
            log=changes, none_ok=True)

        if address_fields is None:
            # Address does not exist; add address
            add_address = True
            db_address_name = None
        elif len(address_fields) == 1:
            # Address does exist; do not add address
            add_address = False
            db_address_name = address_fields["name"]

        # Test if there is already an identical address without the AddressID
        if not add_address:
            keys = ('address_line1', 'address_line2', 'city', 'pincode')
            filters = {}
            for key in keys:
                if address_dict[key] is not None:
                    filters[key] = address_dict[key]

            address_queries = frappe.db.get_values(
                "Address",
                filters=filters,
                fieldname="name")

            if len(address_queries) == 1:
                # We have found a matching address; add eBay AddressID
                db_address_name = address_queries[0][0]
                address_doc = frappe.get_doc("Address", db_address_name)
                address_doc.ebay_address_id = ebay_address_id
                for link in address_doc.links:
                    if (link.link_doctype == 'Customer'
                            and link.link_name == db_cust_name):
                        # A dynamic link to the customer exists
                        break
                else:
                    # There was no link; add one
                    link_doc = address_doc.append('links')
                    link_doc.link_doctype = 'Customer'
                    link_doc.link_name = db_cust_name
                address_doc.save()
                updated_db = True

        # Check that customer has a name, not just an eBay user id,
        # and the the Address name is not just the ebay_user_id.
        # If not, update with new name if assume_shipping_name_is_ebay_name
        if cust_fields is not None and assume_shipping_name_is_ebay_name:
            if (db_cust_customer_name == ebay_user_id
                    and customer_dict["customer_name"] != ebay_user_id):
                new_name = customer_dict["customer_name"]
                if frappe.db.exists('Customer', new_name):
                    # Complicated rename to avoid existing entries
                    for i in range(1, 100):
                        new_name = customer_dict["customer_name"] + '-' + str(i)
                        if not frappe.db.exists('Customer', new_name):
                            frappe.rename_doc('Customer',
                                              db_cust_name, new_name)
                            break
                    else:
                        raise ValueError(
                            'Too many duplicate entries of this customer name!')
                else:
                    # Simple rename
                    frappe.rename_doc(
                        'Customer', db_cust_name,
                        new_name)
                # Update links in changes (to avoid validation failure):
                for change in changes:
                    if change['customer'] == db_cust_name:
                        change['customer'] = new_name
                # Update any Sales Invoices that are in 'draft' status
                for rows in frappe.get_all(
                        'Sales Invoice',
                        filters={'customer_name': ebay_user_id,
                                 'docstatus': 0}):
                    sinv_doc = frappe.get_doc('Sales Invoice', rows['name'])
                    sinv_doc.customer_name = customer_dict["customer_name"]
                    sinv_doc.save()
                db_cust_name = new_name
                debug_msgprint('Updated name: ' + ebay_user_id + ' -> ' +
                               new_name)
                changes.append({"ebay_change": "Updated name",
                                "ebay_user_id": ebay_user_id,
                                "customer_name": customer_dict["customer_name"],
                                "customer": db_cust_name,
                                "address": db_address_name,
                                "ebay_order": None})
                updated_db = True

    # Add address if required
    if add_address:
        if db_cust_name is None:
            # Find new customer 'name' field
            db_cust_name = db_get_ebay_doc(
                "Customer", ebay_user_id, fields=["name"],
                log=changes, none_ok=False)["name"]
        # Add link
        address_dict['links'] = [{
            'link_doctype': 'Customer',
            'link_name': db_cust_name}]
        address_doc = frappe.get_doc(address_dict)
        try:
            address_doc.insert()

        except frappe.DuplicateEntryError as e:
            # An address based on address_title autonaming already exists
                # Get new doc, add a digit to the name and retry
            frappe.db.rollback()
            for suffix_id in range(1, maximum_address_duplicates+1):
                address_doc = frappe.get_doc(address_dict)
                # Hackily patch out autoname function and do it by hand
                address_doc.autoname = MethodType(lambda self: None,
                                                  address_doc)
                address_doc.name = (cstr(address_doc.address_title).strip()
                                    + "-"
                                    + cstr(address_doc.address_type).strip()
                                    + "-" + str(suffix_id))
                try:
                    address_doc.insert()
                    break
                except frappe.DuplicateEntryError:
                    frappe.db.rollback()
                    continue
            else:
                raise ValueError('Too many duplicate entries of this address!')
        updated_db = True

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return None


def create_ebay_order(order_dict, changes, order):
    """Process an eBay order and add eBay order document.
    Does not duplicate entries where possible.

    order_dict - A dictionary ready to create a eBay order doctype.
    changes - A sync log list to append to.

    Returns a list of dictionaries for eBay sync log entries."""

    if changes is None:
        changes = []

    updated_db = False

    ebay_order_id = order_dict['ebay_order_id']
    ebay_user_id = order_dict['ebay_user_id']

    order_fields = db_get_ebay_doc(
        "eBay order", ebay_order_id, fields=["name", "address"],
        log=changes, none_ok=True)

    if order_fields is None:
        # Order does not exist, create eBay order

        cust_fields = db_get_ebay_doc(
            "Customer", ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)

        order_doc = frappe.get_doc(order_dict)
        order_doc.insert()
        debug_msgprint('Adding eBay order: ' + ebay_user_id + ' : ' +
                       ebay_order_id)
        changes.append({"ebay_change": "Adding eBay order",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": cust_fields['customer_name'],
                        "customer": cust_fields['name'],
                        "address": order_dict['address'],
                        "ebay_order": order_doc.name})
        updated_db = True

    else:
        # Order already exists
        # TODO Check if status of order has changed, and if so update??
        # TODO - Should probably check correct customer is linked
        cust_fields = db_get_ebay_doc(
            "Customer", ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)
        debug_msgprint('eBay order already exists: ' + ebay_user_id + ' : ' +
                       ebay_order_id)
        changes.append({"ebay_change": "eBay order already exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": cust_fields["customer_name"],
                        "customer": cust_fields["name"],
                        "address": order_fields['address'],
                        "ebay_order": order_fields["name"]})

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return None


def create_sales_invoice(order_dict, order, changes):
    """
    Create a Sales Invoice from the eBay order.
    """
    updated_db = False

    ebay_order_id = order_dict['ebay_order_id']
    ebay_user_id = order_dict['ebay_user_id']

    order_fields = db_get_ebay_doc(
        "eBay order", ebay_order_id,
        fields=["name", "customer", "customer_name",
                "address", "ebay_order_id"],
        log=changes, none_ok=False)

    db_cust_name = order_fields['customer']

    # Get from existing linked sales order
    sinv_fields = db_get_ebay_doc(
        "Sales Invoice", ebay_order_id, fields=["name"],
        log=changes, none_ok=True)

    if sinv_fields is not None:
        # Linked sales invoice exists
        debug_msgprint('Sales Invoice already exists: '
                       + ebay_user_id + ' : ' + sinv_fields['name'])
        changes.append({"ebay_change": "Sales Invoice already exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": order_fields['customer_name'],
                        "customer": db_cust_name,
                        "address": order_fields['address'],
                        "ebay_order": order_fields['name']})
        return

    # No linked sales invoice - check for old unlinked sales invoice
    test_title = db_cust_name + "-" + ebay_order_id
    query = frappe.get_all("Sales Invoice", filters={"title": test_title})
    if len(query) > 2:
        raise ErpnextEbaySyncError(
            "Multiple Sales Invoices with title {}!".format(test_title))
    if len(query) == 1:
        # Old sales invoice without link - don't interfere
        debug_msgprint('Old Sales Invoice exists: '
                       + ebay_user_id + ' : ' + query[0]['name'])
        changes.append({"ebay_change": "Old Sales Invoice exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": order_fields['customer_name'],
                        "customer": db_cust_name,
                        "address": order_fields['address'],
                        "ebay_order": order_fields['name']})
        return

    if order['OrderStatus'] != 'Completed':
        # This order has not been paid yet
        # Consequently we will not generally have a shipping address, and
        # so cannot correctly assign VAT. We will therefore not create
        # the sales invoice yet.
        debug_msgprint('Order has not yet been paid: '
                       + ebay_user_id + ' : ' + order_fields['ebay_order_id'])
        changes.append({"ebay_change": "Order not yet paid",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": order_fields['customer_name'],
                        "customer": db_cust_name,
                        "address": order_fields['address'],
                        "ebay_order": order_fields['name']})
        return
    # Create a sales invoice

    # eBay date format: YYYY-MM-DDTHH:MM:SS.SSSZ
    posting_date = datetime.datetime.strptime(
        order['CreatedTime'][:-1] + 'UTC', '%Y-%m-%dT%H:%M:%S.%f%Z')
    order_status = order['OrderStatus']
    item_list = []
    payments = []
    taxes = []

    amount_paid_dict = order['AmountPaid']
    if amount_paid_dict['_currencyID'] == 'GBP':
        amount_paid = float(amount_paid_dict['value'])
    else:
        amount_paid = -1.0

    sku_list = []

    sum_inc_vat = 0.0
    sum_exc_vat = 0.0
    sum_vat = 0.0
    sum_paid = 0.0
    shipping_cost = 0.0

    transactions = order['TransactionArray']['Transaction']
    cust_email = transactions[0]['Buyer']['Email']

    # Find the correct VAT rate
    country_name = order['ShippingAddress']['CountryName']
    if country_name is None:
        raise ErpnextEbaySyncError(
            'No country for this order for user {}!'.format(ebay_user_id))
    income_account = determine_income_account(country_name)
    vat_rate = VAT_RATES[income_account]

    # TODO
    # Transaction.BuyerCheckoutMessage
    # Transaction.FinalValueFee
    # isGSP = TransactionArray.Transaction.ContainingOrder.IsMultiLegShipping
    # Transaction.ContainingOrder.MonetaryDetails.Payments.Payment.PaymentStatus
    # Transaction.MonetaryDetails.Payments.Payment.PaymentStatus

    for transaction in transactions:

        if transaction['Buyer']['Email'] != cust_email:
            raise ValueError('Multiple emails for this buyer?')

        # Vat Status
        #NoVATTax	VAT is not applicable
        #VATExempt	Residence in a country with VAT and user is registered as VAT-exempt
        #VATTax	Residence in a country with VAT and user is not registered as VAT-exempt
        #vat_status = transaction['Buyer']['VATStatus']

        shipping_cost_dict = transaction['ActualShippingCost']
        handling_cost_dict = transaction['ActualHandlingCost']
        if shipping_cost_dict['_currencyID'] == 'GBP':
            shipping_cost += float(shipping_cost_dict['value'])
        if handling_cost_dict['_currencyID'] == 'GBP':
            shipping_cost += float(handling_cost_dict['value'])

        qty = float(transaction['QuantityPurchased'])
        try:
            sku = transaction['Item']['SKU']
            sku_list.append(sku)
            # Only allow valid SKU
        except KeyError:
            debug_msgprint(
                'Order {} failed: One of the items did not have an SKU'.format(
                    ebay_order_id))
            sync_error(changes, 'An item did not have an SKU',
                       ebay_user_id, customer_name=db_cust_name)
            raise ErpnextEbaySyncError(
                'An item did not have an SKU for user {}'.format(ebay_user_id))
        if not frappe.db.exists('Item', sku):
            debug_msgprint('Item not found?')
            raise ErpnextEbaySyncError(
                'Item {} not found for user {}'.format(sku, ebay_user_id))

        ebay_price = float(transaction['TransactionPrice']['value'])
        if ebay_price <= 0.0:
            raise ValueError('TransactionPrice Value <= 0.0')

        inc_vat = ebay_price
        exc_vat = round(float(inc_vat) / (1.0 + vat_rate), 2)
        vat = inc_vat - exc_vat

        sum_inc_vat += inc_vat
        sum_exc_vat += exc_vat
        sum_vat += vat * qty
        sum_paid += inc_vat * qty

        # Get item description in case it is empty, and we need to insert
        # filler text to avoid MandatoryError
        description = frappe.get_value('Item', sku, 'description')
        if not strip_html(cstr(description)).strip():
            description = '(no item description)'

        item_list.append({
                "item_code": sku,
                "description": description,
                "warehouse": "Mamhilad - URTL",
                "qty": qty,
                "rate": exc_vat,
                "valuation_rate": 0.0,
                "income_account": income_account,
                "expense_account": "Cost of Goods Sold - URTL",
                "cost_center": "Main - URTL"
         })

    if shipping_cost > 0.0001:
        # Add a single line item for shipping services

        inc_vat = shipping_cost
        exc_vat = round(float(inc_vat) / (1.0 + vat_rate), 2)
        vat = inc_vat - exc_vat

        sum_inc_vat += inc_vat
        sum_exc_vat += exc_vat
        sum_vat += vat
        sum_paid += inc_vat

        item_list.append({
            "item_code": SHIPPING_ITEM,
            "description": "Shipping costs (from eBay)",
            "warehouse": "Mamhilad - URTL",
            "qty": 1.0,
            "rate": exc_vat,
            "valuation_rate": 0.0,
            "income_account": income_account,
            "expense_account": "Shipping - URTL"
        })

    # Taxes are a single line item not each transaction
    if VAT_RATES[income_account] > 0.00001:
        taxes.append({
                    "charge_type": "Actual",
                    "description": "VAT {}%".format(VAT_PERCENT[income_account]),
                    "account_head": "VAT - URTL",
                    "rate": VAT_PERCENT[income_account],
                    "tax_amount": sum_vat})

    checkout = order['CheckoutStatus']
    if checkout['Status'] == 'Complete':
        if checkout['PaymentMethod'] in ('PayOnPickup', 'CashOnPickup'):
            # Cash on delivery - may not yet be paid (set to zero)
            payments.append({"mode_of_payment": "Cash",
                             "amount": 0.0})
        elif checkout['PaymentMethod'] == 'PayPal':
            # PayPal - add amount as it has been paid
            if amount_paid > 0.0:
                payments.append({"mode_of_payment": "Paypal",
                                "amount": amount_paid})
        elif checkout['PaymentMethod'] == 'PersonalCheck':
            # Personal cheque - may not yet be paid (set to zero)
            payments.append({"mode_of_payment": "Cheque",
                             "amount": 0.0})
        elif checkout['PaymentMethod'] == 'MOCC':
            # Postal order/banker's draft - may not yet be paid (set to zero)
            payments.append({"mode_of_payment": "eBay",
                             "amount": 0.0})

    title = 'eBay: {} [{}]'.format(
        order_fields['customer_name'],
        ', '.join(sku_list))

    sinv_dict = {
        "doctype": "Sales Invoice",
        "naming_series": "SINV-",
        "title": title,
        "customer": db_cust_name,
        "ebay_order_id": ebay_order_id,
        "contact_email": cust_email,
        "posting_date": posting_date,
        "posting_time": "00:00:00",
        "due_date": posting_date,
        "set_posting_time": 1,
        "selling_price_list": "Standard Selling",
        "price_list_currency": "GBP",
        "price_list_exchange_rate": 1,
        "ignore_pricing_rule": 1,
        "apply_discount_on": "Net Total",
        "status": "Draft",
        "update_stock": 1,
        "is_pos": 1,
        "taxes": taxes,
        "payments": payments,
        "items": item_list,
        "notification_email_address": cust_email,
        "notify_by_email": 1}

    sinv = frappe.get_doc(sinv_dict)

    sinv.insert()
    #si.submit()

    if abs(amount_paid - sum_paid) > 0.005:
        sinv.add_comment('sync_orders: Unable to match totals - '
                         + 'please check this order manually.')

    updated_db = True

    debug_msgprint('Adding Sales Invoice: ' + ebay_user_id + ' : ' + sinv.name)
    changes.append({"ebay_change": "Adding Sales Invoice",
                    "ebay_user_id": ebay_user_id,
                    "customer_name": order_fields['customer_name'],
                    "customer": db_cust_name,
                    "address": order_fields['address'],
                    "ebay_order": order_fields['name']})

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return


def determine_income_account(country):
    """Determine correct EU or non-EU income account."""
    if not country or country.lower() == "united kingdom":
        return "Sales - URTL"

    if country.lower() in EU_COUNTRIES:
        return "Sales - URTL"

    return "Sales Non EU - URTL"


def sanitize_postcode(in_postcode):
    """Take a UK postcode and tidy it up (spacing and capitals)."""

    postcode = in_postcode.strip().replace(' ', '').upper()
    if (6 > len(postcode) > 8):
        raise ValueError('Unknown postcode type!')

    # A single space always precedes the last three characters of a UK postcode
    postcode = postcode[:-3] + ' ' + postcode[-3:]

    return postcode


def sync_error(changes, error_message, ebay_user_id=None, customer_name=None,
               customer=None, address=None, ebay_order=None):
    """An error was encountered during synchronization.
    Log the error message to the change log.
    """
    changes.append({"ebay_change": error_message,
                    "ebay_user_id": ebay_user_id,
                    "customer_name": customer_name,
                    "customer": customer,
                    "address": address,
                    "ebay_order": ebay_order})


def db_get_ebay_doc(doctype, ebay_id, fields=None, log=None, none_ok=True,
                    ebay_id_name=None):
    """Get document with matching ebay_id from database.

    Search in the database for document with matching ebay_id_name = ebay_id.
    If fields is None, get the document and return as_dict().
    If fields is not None, return the dict of fields for that for that document.

    If more than one customer found raise an error.
    If no customers found and none_ok is False raise an error, else
    return None.
    """

    if ebay_id_name is None:
        ebay_id_name = EBAY_ID_NAMES[doctype]

    error_message = None

    if fields is None:
        fields_search = ["name"]
    else:
        fields_search = fields

    doc_queries = frappe.db.get_all(
        doctype,
        filters={ebay_id_name: ebay_id},
        fields=fields_search)

    if len(doc_queries) == 1:
        if fields is None:
            db_doc_name = doc_queries[0]['name']
            retval = frappe.get_doc(doctype, db_doc_name).as_dict()
        else:
            retval = doc_queries[0]
    elif len(doc_queries) == 0:
        if none_ok:
            retval = None
        else:
            error_message = "No {} found with matching {} = {}!".format(
                doctype, ebay_id_name, ebay_id)
    else:
        error_message = "Multiple {} found with matching {} = {}!".format(
            doctype, ebay_id_name, ebay_id)

    # Print/log error message
    if error_message is not None:
        if log is None:
            frappe.throw(error_message)
        else:
            errstring = ebay_id_name + ' : ' + ebay_id
            error_message = '{}\n{}'.format(log, error_message)
            sync_error(log, error_message, customer_name=errstring)
            raise ErpnextEbaySyncError(error_message)

    return retval
