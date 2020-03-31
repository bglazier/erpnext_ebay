# -*- coding: utf-8 -*-

import sys
import datetime
import html
import traceback
import re
from types import MethodType

from .country_data import lowercase_country_dict
from iso3166 import countries, countries_by_name

import frappe
from frappe import msgprint, _
from frappe.utils import cstr, strip_html

from erpnext import get_default_currency
from erpnext.setup.utils import get_exchange_rate

from .ebay_requests import get_orders
from .ebay_constants import EBAY_TRANSACTION_SITE_IDS

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
EU_COUNTRIES = ['Austria', 'Belgium', 'Bulgaria', 'Croatia', 'Cyprus',
                'Czech Republic', 'Denmark', 'Estonia', 'Finland', 'France',
                'Germany', 'Greece', 'Hungary', 'Ireland', 'Italy', 'Latvia',
                'Lithuania', 'Luxembourg', 'Malta', 'Netherlands', 'Poland',
                'Portugal', 'Romania', 'Slovakia', 'Slovenia', 'Spain',
                'Sweden', 'United Kingdom']

EBAY_ID_NAMES = {'Customer': 'ebay_user_id',
                 'Address': 'ebay_address_id',
                 'eBay order': 'ebay_order_id',
                 'Sales Invoice': 'ebay_order_id'}

# Disagreements between iso3166 and Frappe's country list
# Key = ISO code, value = Frappe docname
ISO_COUNTRIES_TO_DB = {'Cabo Verde': 'Cape Verde',
                       'Congo, Democratic Republic of the':
                           'Congo, The Democratic Republic of the',
                       'Czechia': 'Czech Republic',
                       "Côte d'Ivoire": 'Ivory Coast',
                       'Eswatini': 'Swaziland',  # old country name
                       'Holy See': 'Holy See (Vatican City State)',
                       'Iran, Islamic Republic of': 'Iran',
                       "Korea, Democratic People's Republic of":
                           'Korea, Democratic Peoples Republic of',
                       "Kosovo": None,  # No entry
                       "Lao People's Democratic Republic":
                           'Lao Peoples Democratic Republic',
                       'North Macedonia': 'Macedonia',  # old country name
                       'Palestine, State of': 'Palestinian Territory, Occupied',
                       'Syrian Arab Republic': 'Syria',
                       'Taiwan, Province of China': 'Taiwan',
                       'Tanzania, United Republic of': 'Tanzania',
                       'United Kingdom of Great Britain and Northern Ireland':
                           'United Kingdom',
                       'United States of America': 'United States',
                       'Viet Nam': 'Vietnam'}
ISO_COUNTRIES_TO_DB_LOWERCASE = {key.lower(): value for key, value
                                 in ISO_COUNTRIES_TO_DB.items()}
APOLITICAL_COUNTRIES_NAMES = {x.apolitical_name.lower(): x.name
                              for x in countries_by_name.values()}
# Convert ISO names to Frappe country names
for short_name, iso_name in APOLITICAL_COUNTRIES_NAMES.items():
    if iso_name in ISO_COUNTRIES_TO_DB:
        APOLITICAL_COUNTRIES_NAMES[short_name] = ISO_COUNTRIES_TO_DB[iso_name]

EXTRA_COUNTRIES = {
    'america': 'United States',
    'bolivia': 'Bolivia, Plurinational State of',
    'falklands': 'Falkland Islands (Malvinas)',
    'falkland islands': 'Falkland Islands (Malvinas)',
    'france métropolitaine': 'France',
    'great britain': 'United Kingdom',
    'great britain and northern ireland': 'United Kingdom',
    'litauen': 'Lithuania',
    'laos': 'Lao Peoples Democratic Republic',
    'micronesia': 'Micronesia, Federated States of',
    'north korea': 'Korea, Democratic Peoples Republic of',
    'russia': 'Russian Federation',
    'south korea': 'Korea, Republic of',
    'venezuela': 'Venezuela, Bolivarian Republic of'
    }

COMPANY_ACRONYM = 'URTL'
WAREHOUSE = f'Mamhilad - {COMPANY_ACRONYM}'
SHIPPING_ITEM = 'ITEM-00358'
CAR_ITEM = 'ITEM-11658'

VAT_RATES = {f'Sales - {COMPANY_ACRONYM}': 0.2,
             f'Sales Non EU - {COMPANY_ACRONYM}': 0.0}
VAT_PERCENT = {k: 100*v for k, v in VAT_RATES.items()}


class ErpnextEbaySyncError(Exception):
    pass


def debug_msgprint(message):
    """Simple wrapper for msgprint that also prints to the console.

    Doesn't msgprint if msgprint_debug is not true.
    """
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
    orders, num_days = get_orders(order_status='Completed')

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
                # Identify the eBay site on which the item was listed.
                try:
                    site_id_order = order[
                        'TransactionArray']['Transaction'][0]['Item']['Site']
                except (KeyError, TypeError) as e:
                    msgprint_log.append(
                        'WARNING: unable to identify site ID from:'
                        + '\n{}\n{}'.format(
                            order['TransactionArray'], str(e)))

                # Create/update Customer
                cust_details, address_details = extract_customer(order)
                create_customer(cust_details, address_details, changes)

                # Create/update eBay Order
                order_details = extract_order_info(order, changes)
                create_ebay_order(order_details, changes, order)

                # Create/update Sales Invoice
                create_sales_invoice(order_details, order, ebay_site_id,
                                     site_id_order, msgprint_log, changes)
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
            log.insert(ignore_permissions=True)
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

        # Find the system name for the country
        db_country = sanitize_country(country)

        if db_country is None:
            if address_line2:
                address_line2 = address_line2 + '\n' + country
            else:
                address_line2 = country
            country = None
        else:
            country = db_country

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
        frappe.db.set_value('Customer', db_cust_name, 'represents_company', None)  # Workaround
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

        db_address_name = db_get_ebay_doc(
            "Address", ebay_address_id, fields=["name"],
            log=changes, none_ok=False)["name"]
    else:
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
                  "address": db_address_name}

    return order_dict


def create_ebay_order(order_dict, changes, order):
    """Process an eBay order and add eBay order document.
    Does not duplicate entries where possible.

    order_dict - A dictionary ready to create a eBay order doctype.
    changes - A sync log list to append to.

    Returns a list of dictionaries for eBay sync log entries."""

    # OrderID will change once order is paid, so don't create eBay Order
    # for incomplete order.

    if changes is None:
        changes = []

    updated_db = False

    ebay_order_id = order_dict['ebay_order_id']
    ebay_user_id = order_dict['ebay_user_id']

    if (order['OrderStatus'] != 'Completed'
            or order['CheckoutStatus']['Status'] != 'Complete'):
        debug_msgprint('Order not complete: ' + ebay_user_id +
                       ' : ' + ebay_order_id)
        return

    order_fields = db_get_ebay_doc(
        "eBay order", ebay_order_id, fields=["name", "address"],
        log=changes, none_ok=True)

    if order_fields is None:
        # Order does not exist, create eBay order

        cust_fields = db_get_ebay_doc(
            "Customer", ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)

        order_doc = frappe.get_doc(order_dict)
        order_doc.insert(ignore_permissions=True)
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


def create_sales_invoice(order_dict, order, ebay_site_id, site_id_order,
                         msgprint_log, changes):
    """
    Create a Sales Invoice from the eBay order.
    """
    updated_db = False

    # Don't create SINV from incomplete order
    if (order['OrderStatus'] != 'Completed'
            or order['CheckoutStatus']['Status'] != 'Complete'):
        return

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

    # Create a sales invoice

    # eBay date format: YYYY-MM-DDTHH:MM:SS.SSSZ
    if 'PaidTime' in order:
        paid_datetime = order['PaidTime'][:-1] + 'UTC'
    else:
        paid_datetime = order['CreatedTime'][:-1] + 'UTC'
    posting_date = datetime.datetime.strptime(paid_datetime,
                                              '%Y-%m-%dT%H:%M:%S.%f%Z')
    order_status = order['OrderStatus']
    buyer_checkout_message = order.get('BuyerCheckoutMessage', None)
    if buyer_checkout_message:
        buyer_checkout_message = html.escape(buyer_checkout_message,
                                             quote=False)

    item_list = []
    payments = []
    taxes = []

    amount_paid_dict = order['AmountPaid']
    currency = amount_paid_dict['_currencyID']
    amount_paid = float(amount_paid_dict['value'])
    default_currency = get_default_currency()
    if currency != default_currency:
        conversion_rate = get_exchange_rate(currency, default_currency,
                                            posting_date.date())
    else:
        conversion_rate = 1.0

    sku_list = []

    sum_inc_vat = 0.0
    sum_exc_vat = 0.0
    sum_vat = 0.0
    sum_to_pay = 0.0
    shipping_cost = 0.0
    ebay_car = 0.0  # eBay Collect and Remit sales taxes

    transactions = order['TransactionArray']['Transaction']
    cust_email = transactions[0]['Buyer']['Email']

    # Find the correct VAT rate
    country = frappe.db.get_value('Address', order_dict['address'], 'country')
    if country is None:
        raise ErpnextEbaySyncError(
            'No country for this order for user {}!'.format(ebay_user_id))
    income_account = determine_income_account(country)
    vat_rate = VAT_RATES[income_account]

    # TODO
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
        final_value_fee_dict = transaction['FinalValueFee']

        if shipping_cost_dict['_currencyID'] == currency:
            shipping_cost += float(shipping_cost_dict['value'])
        else:
            raise ErpnextEbaySyncError('Inconsistent currencies in order!')
        if handling_cost_dict['_currencyID'] == currency:
            shipping_cost += float(handling_cost_dict['value'])
        else:
            raise ErpnextEbaySyncError('Inconsistent currencies in order!')

        # Final Value Fee currently limited to being in *default* currency or
        # sale currency, and does not include any VAT (for EU sellers).
        if final_value_fee_dict['_currencyID'] == default_currency:
            # final value fee typically in seller currency
            base_final_value_fee = float(final_value_fee_dict['value'])
            final_value_fee = base_final_value_fee / conversion_rate
        elif final_value_fee_dict['_currencyID'] == currency:
            final_value_fee = float(final_value_fee_dict['value'])
            base_final_value_fee = final_value_fee * conversion_rate
        else:
            raise ErpnextEbaySyncError('Inconsistent currencies in order!')

        if transaction['eBayCollectAndRemitTax'] == 'true':
            ebay_car_dict = (
                transaction['eBayCollectAndRemitTaxes']['TotalTaxAmount'])
            if ebay_car_dict['_currencyID'] == currency:
                ebay_car += float(ebay_car_dict['value'])
            else:
                raise ErpnextEbaySyncError('Inconsistent currencies in order!')

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
        sum_to_pay += inc_vat * qty

        # Get item description in case it is empty, and we need to insert
        # filler text to avoid MandatoryError
        description = frappe.get_value('Item', sku, 'description')
        if not strip_html(cstr(description)).strip():
            description = '(no item description)'

        item_list.append({
                "item_code": sku,
                "description": description,
                "warehouse": WAREHOUSE,
                "qty": qty,
                "rate": exc_vat,
                "ebay_final_value_fee": final_value_fee,
                "base_ebay_final_value_fee": base_final_value_fee,
                "valuation_rate": 0.0,
                "income_account": income_account,
                "expense_account": f"Cost of Goods Sold - {COMPANY_ACRONYM}",
                "cost_center": f"Main - {COMPANY_ACRONYM}"
         })

    # Add a single line item for shipping services
    if shipping_cost > 0.0001:

        inc_vat = shipping_cost
        exc_vat = round(float(inc_vat) / (1.0 + vat_rate), 2)
        vat = inc_vat - exc_vat

        sum_inc_vat += inc_vat
        sum_exc_vat += exc_vat
        sum_vat += vat
        sum_to_pay += inc_vat

        item_list.append({
            "item_code": SHIPPING_ITEM,
            "description": "Shipping costs (from eBay)",
            "warehouse": WAREHOUSE,
            "qty": 1.0,
            "rate": exc_vat,
            "valuation_rate": 0.0,
            "income_account": income_account,
            "expense_account": f"Shipping - {COMPANY_ACRONYM}"
        })

    # Add a single line item for eBay Collect and Remit taxes
    if ebay_car > 0.0001:
        item_list.append({
            "item_code": CAR_ITEM,
            "description": "eBay Collect and Remit taxes",
            "warehouse": WAREHOUSE,
            "qty": 1.0,
            "rate": ebay_car,
            "valuation_rate": 0.0,
            "income_account": income_account,
            "expense_account": f"Cost of Goods Sold - {COMPANY_ACRONYM}"
        })
        sum_to_pay += ebay_car

    # Taxes are a single line item not each transaction
    if VAT_RATES[income_account] > 0.00001:
        taxes.append({
                    "charge_type": "Actual",
                    "description": "VAT {}%".format(VAT_PERCENT[income_account]),
                    "account_head": f"VAT - {COMPANY_ACRONYM}",
                    "rate": VAT_PERCENT[income_account],
                    "tax_amount": sum_vat})

    checkout = order['CheckoutStatus']
    submit_on_pay = False
    if checkout['PaymentMethod'] in ('PayOnPickup', 'CashOnPickup'):
        # Cash on delivery - may not yet be paid (set to zero)
        payments.append({"mode_of_payment": "Cash",
                         "amount": 0.0})
    elif checkout['PaymentMethod'] == 'PayPal':
        # PayPal - add amount as it has been paid
        paypal_acct = f'PayPal {currency}'
        if not frappe.db.exists('Mode of Payment', paypal_acct):
            raise ErpnextEbaySyncError(
                f'Mode of Payment "{paypal_acct}" does not exist!')
        if amount_paid > 0.0:
            payments.append({"mode_of_payment": paypal_acct,
                            "amount": amount_paid})
            submit_on_pay = True
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
        "shipping_address_name": order_dict['address'],
        "ebay_order_id": ebay_order_id,
        "ebay_site_id": site_id_order,
        "buyer_message": buyer_checkout_message,
        "contact_email": cust_email,
        "posting_date": posting_date.date(),
        "posting_time": posting_date.time(),
        "due_date": posting_date,
        "set_posting_time": 1,
        "currency": currency,
        "conversion_rate": conversion_rate,
        "ignore_pricing_rule": 1,
        "apply_discount_on": "Net Total",
        "status": "Draft",
        "update_stock": 1,
        "is_pos": 1,
        "taxes": taxes,
        "payments": payments,
        "items": item_list}

    sinv = frappe.get_doc(sinv_dict)

    sinv.insert()

    if abs(amount_paid - sum_to_pay) > 0.005:
        sinv.add_comment(
            'Comment',
            text='sync_orders: Unable to match totals - please check this '
                 + f'order manually ({amount_paid} != {sum_to_pay})')
    elif submit_on_pay:
        # This is an order which adds up and has an approved payment method
        # Submit immediately
        sinv.submit()

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
    if not country or country in EU_COUNTRIES:
        return f"Sales - {COMPANY_ACRONYM}"

    return f"Sales Non EU - {COMPANY_ACRONYM}"


def sanitize_postcode(in_postcode):
    """Take a UK postcode and tidy it up (spacing and capitals)."""

    postcode = in_postcode.strip().replace(' ', '').upper()
    if (6 > len(postcode) > 8):
        raise ValueError('Unknown postcode type!')

    # A single space always precedes the last three characters of a UK postcode
    postcode = postcode[:-3] + ' ' + postcode[-3:]

    return postcode


def sanitize_country(country):
    """Attempt to match the input string with a country.

    Returns a valid Frappe Country document name if one can be matched.
    Returns None if no country can be identified.
    """
    if country is None:
        return None

    # Special quick case for UK names
    if country in ['UK', 'GB', 'Great Britain', 'United Kingdom']:
        return 'United Kingdom'

    # Simple check for country
    country_query = frappe.db.get_value(
        'Country', filters={'name': country}, fieldname='name')
    if country_query:
        return country_query

    # Country codes
    if len(country) < 4:
        try:
            country = countries.get(country).name
            # Translate to Frappe countries
            if country in ISO_COUNTRIES_TO_DB:
                country = ISO_COUNTRIES_TO_DB[country]
        except KeyError:
            # Country code not found
            return None
        return country

    if country is not None:
        country_lower = country.lower()

        country_search_list = [country_lower]
        country_shorter = re.sub(r'\bof\b|\bthe\b', '', country_lower)
        country_search_list.append(country_shorter)

        test_string = re.sub(r'\brepublic\b', '', country_shorter)
        country_search_list.append(test_string)

        test_string = re.sub(r'\bkingdom\b', '', country_shorter)
        country_search_list.append(test_string)
        test_string = re.sub(
            r"\brepublic\b|\bdemocratic\b|\bpeoples\b|\bpeople's\b|"
            + r"\bstate\b|\bstates\b|\bfederated\b", '', country_shorter)
        country_search_list.append(test_string)
        test_string = re.sub(r'\bn\.|\bn\b', 'north', test_string)
        test_string = re.sub(r'\bs\.|\bs\b', 'south', test_string)
        country_search_list.append(test_string)
        test_string = re.sub(r'\bn\.|\bn\b', 'north', country_shorter)
        test_string = re.sub(r'\bs\.|\bs\b', 'south', test_string)
        country_search_list.append(test_string)
        test_string = re.sub(r'\bn\.|\bn\b', 'north', country_lower)
        test_string = re.sub(r'\bs\.|\bs\b', 'south', test_string)
        country_search_list.append(test_string)

        lowercase_country = lowercase_country_dict.get(country_lower, None)
        if lowercase_country:
            country_search_list.append(lowercase_country)

        # Get Frappe countries list
        db_countries_dict = {x['name'].lower(): x['name'] for x in
                             frappe.get_all('Country')}

        for outer_test_country in country_search_list:
            # Loop over increasingly aggressive test strings

            wrapped_list = [outer_test_country]
            if outer_test_country.count(', ') == 1:
                # Unwrap outer test country
                end, _comma, start = outer_test_country.partition(', ')
                outer_test_country = '{} {}'.format(start, end)
                wrapped_list.append(outer_test_country)

            if outer_test_country.count(',') == 0:
                # All possible re-wrappings
                words = outer_test_country.split()
                for i in range(1, len(words)):
                    wrapped = ' '.join(words[i:]) + ', ' + ' '.join(words[:i])
                    wrapped_list.append(wrapped)

            # Try twice - second time with comma unwrapping
            for test_country in wrapped_list:
                # Trim off extraneous commas and extra whitespace
                test_country = ' '.join(test_country.strip(', ').split())

                # Check list of Frappe countries
                if test_country in db_countries_dict:
                    return db_countries_dict[test_country]

                # Check list of ISO-> frappe translations
                if test_country in ISO_COUNTRIES_TO_DB_LOWERCASE:
                    return ISO_COUNTRIES_TO_DB_LOWERCASE[test_country]

                # Check list of apolitical names
                if test_country in APOLITICAL_COUNTRIES_NAMES:
                    return APOLITICAL_COUNTRIES_NAMES[test_country]

                # Check other list of common names
                if test_country in EXTRA_COUNTRIES:
                    return EXTRA_COUNTRIES[test_country]

        # Failed to find a country
        return None


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
