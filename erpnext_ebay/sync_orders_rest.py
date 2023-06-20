# -*- coding: utf-8 -*-
"""Synchronize completed orders and refunds to Sales Invoices
using the REST API (Sell-Fulfillment and Sell-Finances).
"""

import collections
import datetime
import html
import operator
import re
import sys
import traceback

from .country_data import lowercase_country_dict
from iso3166 import countries, countries_by_name

import frappe

from erpnext import get_default_currency
from erpnext.controllers.sales_and_purchase_return import make_return_doc

from .ebay_constants import EBAY_MARKETPLACE_IDS, EU_COUNTRIES
from .ebay_get_requests import ebay_logger
from .ebay_requests_rest import get_orders, get_transactions
from erpnext_ebay.utils.general_utils import divide_rounded

# Option to use eBay shipping address name as customer name.
# eBay does not normally provide buyer name.
assume_shipping_name_is_ebay_name = True

# Output function (or None) for debugging messages (in addition
# to erpnext_ebay logger)
MSGPRINT_DEBUG = lambda *args: None
MSGPRINT_MAIN = frappe.msgprint

# Should we log changes?
use_sync_log = True

# Continue on errors:
continue_on_error = True

# Maximum number of attempts to add duplicate address (by adding -1, -2 etc)
maximum_address_duplicates = 4

# Maximum number of days that can be polled
MAX_DAYS = 90

# Should we create a warranty claim with each refund?
CREATE_WARRANTY_CLAIMS = False

EBAY_ID_NAMES = {'Customer': 'ebay_user_id',
                 'Address': 'ebay_address_id',
                 'eBay order': 'ebay_order_id',
                 'Sales Invoice': 'ebay_order_id'}

# Extra codes not found in iso3166
ISO_EXTRA_CODES = {
    'AA': 'United States',  # APO/FPO addresses
    'AN': 'Netherlands',  # Netherlands Antilles
    'QM': 'Guernsey',  # Backwards-compatibility only
    'QN': 'Svalbard and Jan Mayen',  # Backwards-compatibility only
    'QO': 'Jersey',  # Backwards-compatibility only
    'TP': None,  # No longer in use
    'YU': None,  # No longer in use (Yugoslavia)
    'CustomCode': None,
    'ZZ': None  # Unknown country
}

# Disagreements between iso3166 and Frappe's country list
# Key = ISO code, value = Frappe docname
ISO_COUNTRIES_TO_DB = {
    'Cabo Verde': 'Cape Verde',
    'Congo, Democratic Republic of the':
        'Congo, The Democratic Republic of the',
    'Czechia': 'Czech Republic',
    "Côte d'Ivoire": 'Ivory Coast',
    #'Eswatini': 'Swaziland',  # old country name
    'Holy See': 'Holy See (Vatican City State)',
    'Iran, Islamic Republic of': 'Iran',
    "Korea, Democratic People's Republic of":
        'Korea, Democratic Peoples Republic of',
    "Kosovo": None,  # No entry
    "Lao People's Democratic Republic":
        'Lao Peoples Democratic Republic',
    #'North Macedonia': 'Macedonia',  # old country name
    'Palestine, State of': 'Palestinian Territory, Occupied',
    'Syrian Arab Republic': 'Syria',
    'Taiwan, Province of China': 'Taiwan',
    'Tanzania, United Republic of': 'Tanzania',
    'Türkiye': 'Turkey',
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
    'danemark': 'Denmark',
    'falklands': 'Falkland Islands (Malvinas)',
    'falkland islands': 'Falkland Islands (Malvinas)',
    'frankreich': 'France',
    'france métropolitaine': 'France',
    'great britain': 'United Kingdom',
    'great britain and northern ireland': 'United Kingdom',
    'ungheria': 'Hungary',
    'litauen': 'Lithuania',
    'laos': 'Lao Peoples Democratic Republic',
    'micronesia': 'Micronesia, Federated States of',
    'north korea': 'Korea, Democratic Peoples Republic of',
    'rumänien': 'Romania',
    'russia': 'Russian Federation',
    'south korea': 'Korea, Republic of',
    'venezuela': 'Venezuela, Bolivarian Republic of',
    'swaziland': 'Eswatini',
    'macedonia': 'North Macedonia'
    }

COMPANY_ACRONYM = frappe.get_all('Company', fields=['abbr'])[0].abbr
WAREHOUSE = f'Main - {COMPANY_ACRONYM}'
SHIPPING_ITEM = 'ITEM-00358'
DEDUCT_UK_VAT = True

TAX_DESCRIPTION = {
    'STATE_SALES_TAX': 'US state sales tax',
    'GST': 'AU/NZ Goods and Services Tax',
    'IMPORT_VAT': 'French import VAT',
    'UK_VAT': 'UK VAT',
    'EU_VAT': 'EU VAT',
    'NOR_VAT': 'Norwegian VAT'
}

VAT_RATES = {
    f'Sales - {COMPANY_ACRONYM}': 0.2,
    f'Sales EU - {COMPANY_ACRONYM}': 0.0,
    f'Sales Non-EU - {COMPANY_ACRONYM}': 0.0
}
VAT_PERCENT = {k: 100*v for k, v in VAT_RATES.items()}

# Fee type for (non-refundable) fee type
EBAY_FIXED_FEE = 'FINAL_VALUE_FEE_FIXED_PER_ORDER'

# Word used to describe refund
REFUND_NAME = {'PARTIALLY_REFUNDED': 'Partial', 'FULLY_REFUNDED': 'Full'}


class ErpnextEbaySyncError(Exception):
    pass


def debug_msgprint(message, msgprint=None):
    """Simple wrapper for a debug printing function

    Doesn't msgprint if msgprint is not true.
    """
    ebay_logger().debug(message)
    if msgprint:
        msgprint(message)


@frappe.whitelist()
def sync_orders(num_days=None, sandbox=False, debug_print=MSGPRINT_DEBUG,
                main_print=MSGPRINT_MAIN):
    """
    Pulls the latest orders from eBay. Creates Sales Invoices for sold items.

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

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay orders...')

    # Load orders from Ebay
    if num_days is None:
        num_days = int(frappe.get_value(
            'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))
    orders = get_orders(min(num_days, MAX_DAYS), sandbox=sandbox)

    # Get earliest creation date
    creation_dates = []
    for order in orders:
        creation_dates.append(datetime.datetime.strptime(
            order['creation_date'][:-1], '%Y-%m-%dT%H:%M:%S.%f').date()
        )
    trans_start_date = min(creation_dates)
    trans_end_date = datetime.datetime.utcnow().date()

    # Load transactions from eBay
    transactions = get_transactions(start_date=trans_start_date,
                                    end_date=trans_end_date, sandbox=sandbox)
    trans_by_order = collections.defaultdict(list)
    for transaction in transactions:
        order_id = transaction['order_id']
        if not order_id:
            # Some transactions put the order ID in the references, not the
            # order_id fields...
            order_ids = []
            for r in (transaction.get('references') or []):
                if r['reference_type'] == 'ORDER_ID':
                    order_ids.append(r['reference_id'])
            if len(order_ids) == 1:
                order_id = order_ids[0]
        if order_id:
            trans_by_order[order_id].append(transaction)

    # Create a synchronization log
    log_dict = {"doctype": "eBay sync log",
                "name": frappe.generate_hash('eBay sync log', 20),
                "ebay_sync_datetime": datetime.datetime.now(),
                "ebay_sync_days": num_days,
                "ebay_log_table": []}
    changes = []
    msgprint_log = []

    try:
        for order in orders:
            try:
                # Identify the eBay site on which the item was listed.
                listing_site = 'EBAY_UNKNOWN'
                purchase_site = 'EBAY_UNKNOWN'
                try:
                    listing_marketplaces = {
                        x['listing_marketplace_id'] for x in order['line_items']
                    }
                    purchase_marketplaces = {
                        x['purchase_marketplace_id']
                        for x in order['line_items']
                    }
                    if len(listing_marketplaces) != 1:
                        msgprint_log.append(
                            'WARNING: unable to identify listing eBay site '
                            + f"from \n{order['line_items']}\n")
                    else:
                        listing_site_id, = listing_marketplaces
                        listing_site = EBAY_MARKETPLACE_IDS[listing_site_id]
                    if len(purchase_marketplaces) != 1:
                        msgprint_log.append(
                            'WARNING: unable to identify purchase eBay site '
                            + f"from \n{order['line_items']}\n")
                    else:
                        purchase_site_id, = purchase_marketplaces
                        purchase_site = EBAY_MARKETPLACE_IDS[purchase_site_id]
                except (KeyError, TypeError) as e:
                    msgprint_log.append(
                        'WARNING: unable to identify listing/purchase eBay site '
                        + 'from\n{}\n{}'.format(
                            order['line_items'], str(e)))

                # Create/update Customer
                cust_details, address_details = extract_customer(order)
                db_cust_name, db_address_name = create_customer(
                    cust_details, address_details, changes, debug_print)

                # Create/update eBay Order
                order_details, payment_status = extract_order_info(
                    order, db_cust_name, db_address_name, changes)
                create_ebay_order(order_details, payment_status,
                                  changes, debug_print)

                # Create Sales Invoice
                create_sales_invoice(
                    order_details, order, listing_site, purchase_site,
                    trans_by_order, changes, debug_print
                )

                # Create Sales Invoice refund
                create_return_sales_invoice(
                    order_details, order, changes, debug_print
                )

            except ErpnextEbaySyncError as e:
                # Continue to next order
                frappe.db.rollback()
                msgprint_log.append(str(e))
                debug_print(f'ORDER FAILED {order.get("order_id")}\n{str(e)}')
                ebay_logger().error(
                    f'Sync order {order.get("order_id")} failed', exc_info=e)
            except Exception as e:
                # Continue to next order
                frappe.db.rollback()
                err_msg = traceback.format_exc()
                ebay_logger().error(
                    f'ORDER FAILED {order.get("order_id")}', exc_info=e)
                if not continue_on_error:
                    debug_print(f'ORDER FAILED {order.get("order_id")}')
                    raise
                else:
                    msgprint_log.append(
                        f'ORDER FAILED {order.get("order_id")}:\n{err_msg}')

    finally:
        # Save the log, regardless of how far we got
        frappe.db.commit()
        for change in changes:
            log_dict['ebay_log_table'].append(change)
        log = frappe.get_doc(log_dict)
        if use_sync_log:
            log.flags.name_set = True
            log.insert(ignore_permissions=True)
        else:
            del log
        frappe.db.commit()
    msgprint_log.append('Finished.')
    main_print('\n'.join(msgprint_log))
    return


def extract_customer(order):
    """Process an order, and extract limited customer information.

    order - a single order entry from the eBay Sell Fulfillment API.

    Returns a tuple of two dictionarys.
    The first dictionary is ready to create a Customer Doctype entry.
    The second dictionary is ready to create an Address Doctype entry.
    The second dictionary could be replaced by None if there is no address.
    """

    buyer = order['buyer']
    ebay_user_id = buyer['username']
    order_id = order['order_id']

    fulfillments = order['fulfillment_start_instructions']
    if fulfillments:
        ship_to = fulfillments[0]['shipping_step']['ship_to']
    else:
        ship_to = {}
    shipping_address = ship_to.get('contact_address') or {}

    shipping_name = ship_to.get('full_name')
    address_line1 = shipping_address.get('address_line1')
    address_line2 = shipping_address.get('address_line2')
    city = shipping_address.get('city')
    state = shipping_address.get('state_or_province')
    postcode = shipping_address.get('postal_code')
    country_code = shipping_address.get('country_code')

    email = ship_to.get('email')
    primary_phone = ship_to.get('primary_phone', {})
    phone_number = primary_phone.get('phone_number')

    tax_address = buyer.get('tax_address')
    if tax_address:
        tax_country = sanitize_country_code(tax_address["country_code"]) or "None"
        customer_details = '\n'.join([
            'eBay Tax address details:',
            f'Postal code: {tax_address.get("postal_code", "None")}',
            f'City: {tax_address.get("city", "None")}',
            f'State or province: {tax_address.get("start_or_province", "None")}',
            f'Country: {tax_country}'
        ])
        # If we don't have an address but do have a tax address,
        # set the country
        if not country_code:
            country_code = tax_address.get('country_code')
    else:
        customer_details = None

    # Country is mandatory for Customre, so fall back to UK
    if not country_code:
        country_code = 'GB'

    tax_identifier = buyer.get('tax_identifier')
    if tax_identifier:
        tax_details = [
            tax_identifier.get("tax_identifier_type", ""),
            tax_identifier.get("taxpayer_id", ""),
            tax_identifier.get("issuing_country", "")
        ]
        tax_id = ' '.join(x for x in tax_details if x)
    else:
        tax_id = None

    # Find the system name for the country_name
    db_country = sanitize_country_code(country_code)

    # Strip the silly eBay eVTN from address lines
    if address_line1:
        if is_ebay_evtn(address_line1):
            address_line1 = ''
        elif ' ' in address_line1:
            start, sep, last_word = address_line1.rpartition(' ')
            if is_ebay_evtn(last_word):
                address_line1 = start
    if address_line2:
        if is_ebay_evtn(address_line2):
            address_line2 = ''
        elif ' ' in address_line2:
            start, sep, last_word = address_line2.rpartition(' ')
            if is_ebay_evtn(last_word):
                address_line2 = start

    # Strip out Norwegian VAT declaration, if present
    if db_country == 'Norway' and address_line2 == 'VOEC NO:2024926 Code:Paid':
        address_line2 = ''

    # Tidy up full name, if entirely lower/upper case and not
    # a single word
    if not shipping_name:
        # Skip if there is no shipping name
        pass
    elif ((shipping_name.islower() or shipping_name.isupper()) and
            ' ' in shipping_name):
        shipping_name = shipping_name.title()

    if assume_shipping_name_is_ebay_name:
        customer_name = shipping_name or ebay_user_id
    else:
        customer_name = ebay_user_id

    customer_dict = {
        "doctype": "Customer",
        "customer_name": customer_name,
        "ebay_user_id": ebay_user_id,
        "tax_id": tax_id,
        "customer_group": "Individual",
        "territory": determine_territory(db_country),
        "customer_details": customer_details,
        "customer_type": "Individual"}

    # Rest of the information
    if not address_line1 and address_line2:
        # If first address line is empty, but the second is not,
        # bump into the first address line (which must not be empty)
        address_line1, address_line2 = address_line2, ''

    # Note - the Fulfillment API does not generate an eBay AddressID
    # so we use the Order ID prefixed by 'ORDER_'

    # Prepare the address dictionary
    if postcode is not None and db_country == 'United Kingdom':
        postcode = sanitize_postcode(postcode)
    address_dict = {
        "doctype": "Address",
        "ebay_address_id": f"ORDER_{order_id}",
        "address_title": shipping_name or ebay_user_id,
        "address_type": "Shipping",
        "address_line1": address_line1 or '-',
        "address_line2": address_line2,
        "city": city or '-',
        "state": state,
        "pincode": postcode,
        "country": db_country,
        "phone": phone_number,
        "email_id": email}

    return customer_dict, address_dict


def create_customer(customer_dict, address_dict, changes=None, print_func=None):
    """Process an order and add the customer; add customer address.
    Does not duplicate entries where possible.

    customer_dict - A dictionary ready to create a Customer doctype.
    address_dict - A dictionary ready to create an Address doctype.
    changes - A sync log list to append to.

    Returns the db name of the customer and address.
    """

    if changes is None:
        changes = []

    updated_db = False

    # Test if the customer already exists
    db_cust_name = None
    ebay_user_id = customer_dict['ebay_user_id']
    ebay_address_id = address_dict['ebay_address_id']

    cust_fields = db_get_ebay_doc(
        "Customer", ebay_user_id, fields=["name", "customer_name", "territory"],
        log=changes, none_ok=True)

    if cust_fields is None:
        # We don't have a customer with a matching ebay_user_id
        # Add the customer
        cust_doc = frappe.get_doc(customer_dict)
        cust_doc.insert()
        db_cust_name = cust_doc.name
        frappe.db.set_value('Customer', db_cust_name,
                            'represents_company', None)  # Workaround
        updated_db = True
        debug_msgprint(
            f'Adding a user: {ebay_user_id} : {customer_dict["customer_name"]}',
            print_func)
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
        debug_msgprint(
            f'User already exists: {ebay_user_id} : {db_cust_customer_name}',
            print_func)
        changes.append({"ebay_change": "User already exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": db_cust_customer_name,
                        "customer": db_cust_name,
                        "address": None,
                        "ebay_order": None})

    # Get name of existing address, if one exists
    db_address_name = None
    address_fields = db_get_ebay_doc(
        "Address", ebay_address_id, fields=["name"],
        log=changes, none_ok=True)
    if address_fields:
        db_address_name = address_fields.get('name')

    # Test if there is already an identical address without the AddressID
    if not db_address_name:
        keys = ('address_title', 'address_line1', 'address_line2',
                'city', 'pincode')
        filters = {}
        for key in keys:
            filters[key] = address_dict[key] or ''

        address_queries = frappe.db.get_all(
            "Address",
            fields=["name"],
            filters=filters)

        if len(address_queries) >= 1:
            # We have found a matching address; add eBay AddressID
            db_address_name = address_queries[0].name
            address_doc = frappe.get_doc("Address", db_address_name)
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
            # Update the customer territory, if required
            if cust_fields:
                territory = determine_territory(address_doc.country)
                if territory != cust_fields['territory']:
                    frappe.set_value('Customer', db_cust_name,
                                     'territory', territory)

    # Add address if required
    if not db_address_name:
        # Add link
        address_dict['links'] = [{
            'link_doctype': 'Customer',
            'link_name': db_cust_name}]
        address_doc = frappe.get_doc(address_dict)
        # Frappe automatically generates a name from the address title and
        # address type, and adds a suffix if this already exists. Unfortunately,
        # this breaks if there are special characters, such as apostrophes,
        # in the address title, so let's just do it ourselves...
        address_prefix = (
            frappe.utils.cstr(address_doc.address_title).strip()
            + "-"
            + frappe.utils.cstr(address_doc.address_type).strip()
        )
        address_name = address_prefix
        if frappe.db.exists('Address', address_name):
            for suffix in range(1, maximum_address_duplicates+1):
                address_name = f'{address_prefix}-{suffix}'
                if not frappe.db.exists('Address', address_name):
                    break
            else:
                raise ValueError('Too many duplicate entries of this address!')
        address_doc.name = address_name
        address_doc.flags.name_set = True
        address_doc.insert()

        db_address_name = address_doc.name
        # Update the customer territory, if required
        territory = determine_territory(address_doc.country)
        if territory != frappe.db.get_value('Customer', db_cust_name,
                                            'territory'):
            frappe.set_value('Customer', db_cust_name, 'territory', territory)
        updated_db = True

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return db_cust_name, db_address_name


def extract_order_info(order, db_cust_name, db_address_name, changes=None):
    """Process an order, and extract limited transaction information.
    order - a single order entry from the eBay Fulfillment API.
    db_cust_name - Customer document name
    db_address_name - Address document name
    changes - A sync log list to append to.
    Returns dictionary for eBay order entries, and the order payment status."""

    if changes is None:
        changes = []

    ebay_user_id = order['buyer']['username']

    # Get customer name
    customer_name = frappe.get_value('Customer', db_cust_name, 'customer_name')

    # Return dict of order information, ready for creating an eBay Order
    order_dict = {"doctype": "eBay order",
                  "name": order['order_id'],
                  "ebay_order_id": order['order_id'],
                  "ebay_user_id": ebay_user_id,
                  "customer": db_cust_name,
                  "customer_name": customer_name,
                  "address": db_address_name}

    payment_status = order['order_payment_status']

    return order_dict, payment_status


def create_ebay_order(order_dict, payment_status, changes, print_func):
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

    if payment_status in ('FAILED', 'PENDING'):
        debug_msgprint(f'Order not complete: {ebay_user_id} : {ebay_order_id}',
                       print_func)
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
        debug_msgprint(f'Adding eBay order: {ebay_user_id} : {ebay_order_id}',
                       print_func)
        changes.append({"ebay_change": "Adding eBay order",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": cust_fields['customer_name'],
                        "customer": cust_fields['name'],
                        "address": order_dict['address'],
                        "ebay_order": order_doc.name})
        updated_db = True

    else:
        # Order already exists
        cust_fields = db_get_ebay_doc(
            "Customer", ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)
        debug_msgprint(
            f'eBay order already exists: {ebay_user_id} : {ebay_order_id}',
            print_func)
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


def create_sales_invoice(order_dict, order, listing_site, purchase_site,
                         trans_by_order, changes, print_func):
    """
    Create a Sales Invoice from the eBay order.
    """
    updated_db = False

    # Don't create SINV from incomplete order
    if order['order_payment_status'] in ('FAILED', 'PENDING'):
        return

    ebay_order_id = order_dict['ebay_order_id']
    ebay_user_id = order_dict['ebay_user_id']
    db_cust_name = order_dict['customer']
    db_address_name = order_dict['address']

    # Get from existing linked sales order
    sinv_fields = db_get_ebay_doc(
        "Sales Invoice", ebay_order_id, fields=["name"],
        log=changes, none_ok=True)

    if sinv_fields is not None:
        # Linked sales invoice exists
        debug_msgprint(
            'Sales Invoice already exists: '
            + f'{ebay_user_id} : {sinv_fields["name"]}', print_func)
        changes.append({"ebay_change": "Sales Invoice already exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": order_dict['customer_name'],
                        "customer": db_cust_name,
                        "address": order_dict['address'],
                        "ebay_order": order_dict['name']})
        return

    # No linked sales invoice - check for old unlinked sales invoice
    test_title = db_cust_name + "-" + ebay_order_id
    query = frappe.get_all("Sales Invoice", filters={"title": test_title})
    if len(query) > 2:
        raise ErpnextEbaySyncError(
            f"Multiple Sales Invoices with title {test_title}!")
    if len(query) == 1:
        # Old sales invoice without link - don't interfere
        debug_msgprint(
            f'Old Sales Invoice exists: {ebay_user_id} : {query[0]["name"]}',
            print_func)
        changes.append({"ebay_change": "Old Sales Invoice exists",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": order_dict['customer_name'],
                        "customer": db_cust_name,
                        "address": order_dict['address'],
                        "ebay_order": order_dict['name']})
        return

    # Create a sales invoice

    # eBay date format: YYYY-MM-DDTHH:MM:SS.SSSZ
    posting_date = datetime.datetime.strptime(
        order['creation_date'][:-1] + 'UTC', '%Y-%m-%dT%H:%M:%S.%f%Z')

    # Get Buyer Checkout Message, if any
    buyer_checkout_message = order['buyer_checkout_notes']
    if buyer_checkout_message:
        buyer_checkout_message = html.escape(buyer_checkout_message,
                                             quote=False)

    # Find the VAT rate
    country = frappe.db.get_value('Address', order_dict['address'], 'country')
    if country is None:
        raise ErpnextEbaySyncError(
            f'No country for this order for user {ebay_user_id}!')
    (
        income_account, ship_income_account, tax_income_account
    ) = determine_income_accounts(country)
    territory = determine_territory(country)
    vat_rate = VAT_RATES[income_account]

    # With eBay Managed Payments, only get paid in 'home' currency
    # Need to deal with conversions if paid in foreign currency so that fees
    # (when added later as PINV) will match
    default_currency = get_default_currency()
    price_total = order['pricing_summary']['total']
    currency = price_total['converted_from_currency'] or price_total['currency']
    payments_summary = order['payment_summary']['payments']
    if len(payments_summary) != 1:
        raise ErpnextEbaySyncError(
            f'Order {ebay_order_id} has number of payments != 1!')
    if payments_summary[0]['amount']['currency'] != default_currency:
        raise ErpnextEbaySyncError(
            f'Order {ebay_order_id} has wrong home currency!')
    # total_price INCLUDES Collect and Remit Taxes
    total_price = (
        float(price_total['converted_from_value'] or price_total['value'])
    )

    # Test for CASH_ON_PICKUP order
    cash_on_pickup = payments_summary[0]['payment_method'] == 'CASH_ON_PICKUP'

    # Get the basic details of payouts and item fees
    if cash_on_pickup:

        # Deal with separate fixed and final value fees,
        # and no sale transaction
        transactions_fee = [
            t for t in trans_by_order.get(ebay_order_id, [])
            if t.get('fee_type') == 'FINAL_VALUE_FEE'
        ]
        transactions_fixed = [
            t for t in trans_by_order.get(ebay_order_id, [])
            if t.get('fee_type') == 'FINAL_VALUE_FEE_FIXED_PER_ORDER'
        ]
        if not (transactions_fee and transactions_fixed):
            raise ErpnextEbaySyncError(
                'Could not find transaction matching eBay '
                + f'order {ebay_order_id}!')
        elif len(transactions_fee) > 1:
            raise ErpnextEbaySyncError(
                'Multiple final value fee transactions matching '
                + f'eBay order {ebay_order_id}!')
        elif len(transactions_fixed) > 1:
            raise ErpnextEbaySyncError(
                'Multiple fixed fee transactions matching '
                + f'eBay order {ebay_order_id}!')
        t_amount_fee = transactions_fee[0]['amount']
        t_amount_fixed = transactions_fixed[0]['amount']
        if t_amount_fee['currency'] != default_currency:
            raise ErpnextEbaySyncError(
                f'eBay order {ebay_order_id} non-default fee currency!')
        if t_amount_fixed['currency'] != default_currency:
            raise ErpnextEbaySyncError(
                f'eBay order {ebay_order_id} non-default fixed fee currency!')
        base_fee = float(t_amount_fee['value'])
        base_fixed_fee = float(t_amount_fixed['value'])
        fee_amount = 0.0  # No fee as part of SINV
        p_amount = payments_summary[0]['amount']
        payout_amount = float(
            p_amount['converted_from_value'] or p_amount['value']
        )
        base_payout_amount = float(p_amount['value'])
        conversion_rate = base_payout_amount / payout_amount

        # Divide fees amongst items
        item_value_dict = {
            li['line_item_id']: float(li['line_item_cost']['value'])
            for li in order['line_items']
        }
        base_item_fee_dict = divide_rounded(item_value_dict, base_fee)
        base_fixed_fee_dict = divide_rounded(item_value_dict, base_fixed_fee)
        item_fee_dict = divide_rounded(
            item_value_dict, base_fee / conversion_rate)
        fixed_fee_dict = divide_rounded(
            item_value_dict, base_fixed_fee / conversion_rate)

    else:

        # Get the sale transaction, and get fees from that
        transactions = [
            t for t in trans_by_order.get(ebay_order_id, [])
            if t['transaction_type'] == 'SALE'
        ]
        if not transactions:
            raise ErpnextEbaySyncError(
                f"Could not find transaction matching eBay order {ebay_order_id}!")
        elif len(transactions) > 1:
            raise ErpnextEbaySyncError(
                f"Multiple transactions matching eBay order {ebay_order_id}!")
        transaction = transactions[0]
        t_amount_dict = transaction['amount']

        # Get payout amounts
        if t_amount_dict['currency'] != default_currency:
            raise ErpnextEbaySyncError(
                f'eBay order {ebay_order_id} has payout not in {default_currency}!')
        # Amount of payout in foreign and home currency
        payout_amount = float(
            t_amount_dict['converted_from_value'] or t_amount_dict['value']
        )
        # Total fees (in seller currency)
        # Occasionally there are no fees on the accompanying transaction
        if transaction['total_fee_amount']:
            fee_amount = float(transaction['total_fee_amount']['value'])
        else:
            fee_amount = 0.0
        # Currency payout was converted from, or None if using home currency
        t_currency = t_amount_dict['converted_from_currency']
        if t_currency:
            # Transaction in non-home currency
            if t_currency != currency:
                raise ErpnextEbaySyncError(
                    f'eBay order {ebay_order_id} has inconsistent currencies!')
            ebay_exchange_rate = float(t_amount_dict['exchange_rate'])
            # Calculate fee amount as it will be calculated later (using eBay
            # exchange rate)
            fee_amount_home_currency = round(
                ebay_exchange_rate * float(fee_amount), 2
            )
        else:
            # Transaction in home currency; no conversion needed
            fee_amount_home_currency = fee_amount
            conversion_rate = 1.0
        # Calculate relevant payment amount in local currency so everything
        # will add up later. This is the payout amount PLUS the fees in home
        # currency.
        payment_amount_home_currency = (
            float(t_amount_dict['value']) + fee_amount_home_currency
        )
        if t_currency:
            # Calculate the conversion rate that gets from the payment amount
            # in foreign currency to the payment amount in home currency (not
            # necessarily exactly the eBay rate). This is so when we later
            # deduct the fees based on the foreign fees and eBay exchange rate,
            # we don't lose anything due to rounding error.
            # We need to make sure the exchange rate works in both directions
            # for the rounded totals.
            payment_amount = payout_amount + fee_amount
            conversion_rate = get_magic_exchange_rate(
                ebay_exchange_rate, payment_amount_home_currency,
                payment_amount
            )
            if not conversion_rate:
                raise ErpnextEbaySyncError(
                    f'eBay order {ebay_order_id} conversion rate logic failed!')

        # Collect fees for each item
        item_fee_dict = collections.defaultdict(float)
        fixed_fee_dict = collections.defaultdict(float)
        for order_line_item in (transaction['order_line_items'] or []):
            item_id = order_line_item['line_item_id']
            for marketplace_fee in order_line_item['marketplace_fees']:
                if marketplace_fee['amount']['currency'] != currency:
                    raise ErpnextEbaySyncError(
                        f'Order {ebay_order_id} transactions in wrong currency!'
                    )
                fee = float(marketplace_fee['amount']['value'])
                item_fee_dict[item_id] += fee
                if marketplace_fee['fee_type'] == EBAY_FIXED_FEE:
                    fixed_fee_dict[item_id] += fee

        # Convert eBay fees if required, ensuring they add up
        if conversion_rate == 1.0:
            base_item_fee_dict = item_fee_dict
            base_fixed_fee_dict = fixed_fee_dict
        else:
            base_item_fee_dict = divide_rounded(
                item_fee_dict, fee_amount_home_currency)
            base_fixed_fee_dict = {
                k: round(v * ebay_exchange_rate, 2)
                for k, v in fixed_fee_dict.items()
            }

    # Loop over line items
    sum_vat = 0.0
    sum_line_items = 0.0
    shipping_cost = 0.0
    # Shipping deadlines
    max_delivery_dts = []
    ship_by_dts = []
    # eBay Collect and Remit taxes
    car_references = collections.defaultdict(set)
    car_by_type = collections.defaultdict(float)

    sku_list = []
    sinv_items = []
    for line_item in order['line_items']:
        line_item_id = line_item['line_item_id']
        item_car_total = 0.0
        item_car_reference = None
        # Only allow valid SKU
        sku = line_item['sku']
        if not sku:
            debug_msgprint(
                f'Order {ebay_order_id} failed: Item without SKU', print_func
            )
            sync_error(changes, 'An item did not have an SKU',
                       ebay_user_id, customer_name=db_cust_name)
            raise ErpnextEbaySyncError(
                f'An item did not have an SKU for user {ebay_user_id}')
        if not frappe.db.exists('Item', sku):
            debug_msgprint('Item not found?', print_func)
            raise ErpnextEbaySyncError(
                f'Item {sku} not found for user {ebay_user_id}', print_func)
        sku_list.append(sku)

        # Get qty and description
        qty = line_item['quantity']
        description = frappe.get_value('Item', sku, 'description')
        if not frappe.utils.strip_html(description or '').strip():
            description = '(no item description)'

        # Delivery costs in buyer currency
        shipping_dict = line_item['delivery_cost']['shipping_cost']
        if line_item['delivery_cost']['import_charges']:
            raise NotImplementedError('import_charges')
        if line_item['delivery_cost']['shipping_intermediation_fee']:
            raise NotImplementedError('shipping_intermediation_fee')
        li_shipping_cost = float(
            shipping_dict['converted_from_value'] or shipping_dict['value']
        )
        shipping_cost += li_shipping_cost

        # Check for unhandled taxes
        for tax_item in line_item['taxes'] or []:
            tax_type = tax_item['tax_type']
            if tax_type in ('STATE_SALES_TAX', 'GST', 'VAT', 'IMPORT_VAT'):
                continue  # Appear in eBay Collect and Remit section
            original_address2 = (
                order['fulfillment_start_instructions'][0]['shipping_step']
                ['ship_to']['contact_address']['address_line2']
            )
            norwegian_vat = (
                tax_type is None and country == 'Norway'
                and original_address2 == 'VOEC NO:2024926 Code:Paid'
            )
            if norwegian_vat:
                if line_item['ebay_collect_and_remit_taxes']:
                    for car_item in line_item['ebay_collect_and_remit_taxes']:
                        ebay_ref = car_item.get('ebay_reference') or {}
                        if ebay_ref.get('value') == 'VOEC NO:2024926':
                            car_item['tax_type'] = 'NOR_VAT'
                else:
                    # Special-case Norwegian VAT without CAR - build
                    # CAR reference
                    line_item['ebay_collect_and_remit_taxes'] = [{
                        'tax_type': 'NOR_VAT',
                        'amount': tax_item['amount'],
                        'ebay_reference': {
                            'name': 'VOEC NO',
                            'value': '2024926 Code:Paid'
                        }
                    }]
            elif (tax_type is None) and not float(tax_item['amount']['value']):
                # Tax amount is zero
                pass
            else:
                raise ErpnextEbaySyncError(
                    f'Order {ebay_order_id} has unhandled tax {tax_type}')

        # Check for Collect and Remit taxes
        for car_item in line_item['ebay_collect_and_remit_taxes'] or []:
            tax_type = car_item['tax_type']
            if tax_type not in (
                    'STATE_SALES_TAX', 'GST', 'VAT', 'NOR_VAT', 'IMPORT_VAT'):
                raise ErpnextEbaySyncError(
                    f'Order {ebay_order_id} has unhandled CAR tax {tax_type}')
            if tax_type == 'VAT':
                # Handle UK and EU VAT separately
                tax_type = (
                    'UK_VAT' if territory == 'United Kingdom' else 'EU_VAT'
                )
            # Check currencies
            car_currency = (
                car_item['amount']['converted_from_currency']
                or car_item['amount']['currency']
            )
            if car_currency != currency:
                raise ErpnextEbaySyncError(
                    f'Order {ebay_order_id} has inconsistent tax currencies')
            # Get tax amount
            tax_amount = float(
                car_item['amount']['converted_from_value']
                or car_item['amount']['value']
            )
            car_by_type[tax_type] += tax_amount
            item_car_total += tax_amount
            # Tax reference
            if car_item['ebay_reference']:
                if item_car_reference:
                    raise ErpnextEbaySyncError(
                        f"Order {ebay_order_id} has multiple CAR references "
                        + "on the same item!"
                    )
                item_car_reference = (
                    f"""{car_item['ebay_reference']['name']}: """
                    + f"""{car_item['ebay_reference']['value']}"""
                )
                car_references[tax_type].add(item_car_reference)

        # Check for maximum delivery date/ship by date
        if li_ff := line_item.get('line_item_fulfillment_instructions'):
            if medd := li_ff.get('max_estimated_delivery_date'):
                max_delivery_date = frappe.utils.convert_utc_to_system_timezone(
                    datetime.datetime.fromisoformat(medd.rstrip('Z'))
                ).replace(tzinfo=None)
                max_delivery_dts.append(max_delivery_date)
            if sbd := li_ff.get('ship_by_date'):
                ship_by_date = frappe.utils.convert_utc_to_system_timezone(
                    datetime.datetime.fromisoformat(sbd.rstrip('Z'))
                ).replace(tzinfo=None)
                ship_by_dts.append(ship_by_date)

        # Get price
        li_total = line_item['total']
        # Check buyer currencies match
        if ((li_total['converted_from_currency'] or li_total['currency'])
                != currency):
            raise ErpnextEbaySyncError(
                f'eBay order {ebay_order_id} has inconsistent currencies!')
        # Line item price in buyer currency (after subtracting taxes
        # and shipping)
        ebay_price = float(
            li_total['converted_from_value'] or li_total['value']
        ) - (item_car_total + li_shipping_cost)
        sum_line_items += ebay_price

        # Calculate VAT, pushing rounding error into VAT amount
        # For multi-qty items, prices are rounded on per-qty level
        inc_vat = ebay_price
        exc_vat = qty * round(inc_vat / (qty * (1.0 + vat_rate)), 2)
        vat = inc_vat - exc_vat

        sum_vat += vat

        # Create SINV item
        sinv_items.append({
            "item_code": sku,
            "description": description,
            "warehouse": WAREHOUSE,
            "qty": qty,
            "rate": exc_vat / qty,
            "ebay_final_value_fee": item_fee_dict.get(line_item_id, 0.0),
            "base_ebay_final_value_fee":
                base_item_fee_dict.get(line_item_id, 0.0),
            "ebay_fixed_fee": fixed_fee_dict.get(line_item_id, 0.0),
            "base_ebay_fixed_fee":
                base_fixed_fee_dict.get(line_item_id, 0.0),
            "ebay_collect_and_remit": item_car_total,
            "ebay_collect_and_remit_reference": item_car_reference or '',
            "ebay_order_line_item_id": line_item_id,
            "ebay_item_id": line_item['legacy_item_id'],
            "valuation_rate": 0.0,
            "income_account": income_account,
            "expense_account": f"Cost of Goods Sold - {COMPANY_ACRONYM}"
        })

    # Total of all eBay Collect and Remit taxes
    total_collect_and_remit = sum(car_by_type.values())
    # Total amount for payout before deduction of fees
    payout_subtotal = round(total_price - total_collect_and_remit, 2)

    # Add a single line item for shipping services
    if shipping_cost > 0.0001:

        inc_vat = shipping_cost
        exc_vat = round(inc_vat / (1.0 + vat_rate), 2)
        vat = inc_vat - exc_vat

        sum_vat += vat
        sum_line_items += inc_vat

        sinv_items.append({
            "item_code": SHIPPING_ITEM,
            "description": "Shipping costs (from eBay)",
            "warehouse": WAREHOUSE,
            "qty": 1.0,
            "rate": exc_vat,
            "valuation_rate": 0.0,
            "income_account": ship_income_account,
            "expense_account": f"Cost of Goods Sold - {COMPANY_ACRONYM}"
        })

    sum_line_items = round(sum_line_items, 2)

    # Check line item prices add up as expected (excluding Collect and Remit)
    if sum_line_items != payout_subtotal:
        raise ErpnextEbaySyncError(
            f'Order {ebay_order_id} inconsistent amounts!'
        )

    # Check payout_subtotal - fees = payout_amount
    if round(payout_subtotal - fee_amount, 2) != payout_amount:
        raise ErpnextEbaySyncError(
            f"Order {ebay_order_id} payments don't add up!")

    collect_and_remit_details = []
    for tax_type, tax_amount in car_by_type.items():
        # Add details for each eBay Collect and Remit type
        tax_desc = TAX_DESCRIPTION[tax_type]
        amt = frappe.utils.fmt_money(tax_amount, currency=currency)
        if car_references[tax_type]:
            # This tax has a reference
            if len(car_references[tax_type]) != 1:
                raise ErpnextEbaySyncError(
                    f'Order {ebay_order_id} non-single {tax_type} reference!')
            car_ref, = car_references[tax_type]
            collect_and_remit_details.append(
                f"""<li>{tax_desc} <strong>{amt}</strong><br>{car_ref}</li>"""
            )
        else:
            # This tax has no references
            collect_and_remit_details.append(
                f"""<li>{tax_desc} <strong>{amt}</strong></li>"""
            )
    if collect_and_remit_details:
        collect_and_remit_details = (
            '<ul>' + '\n'.join(collect_and_remit_details) + '</ul>'
        )

    # Taxes are a single line item not each transaction
    if DEDUCT_UK_VAT:
        # If eBay have already deducted UK VAT then no more is payable
        sum_vat -= car_by_type['UK_VAT']
    taxes = []
    if VAT_RATES[income_account] > 0.00001:
        taxes.append({
            "charge_type": "Actual",
            "description": f"VAT {VAT_PERCENT[income_account]}%",
            "account_head": f"VAT - {COMPANY_ACRONYM}",
            "rate": VAT_PERCENT[income_account],
            "tax_amount": sum_vat
        })

    # All payments made by eBay Managed Payments
    # eBay Managed Payments (with/without eBay gift card)
    # Add amount as it has been paid
    # Always use default currency
    ebay_payment_account = f'eBay Managed {default_currency}'
    if not frappe.db.exists('Mode of Payment', ebay_payment_account):
        raise ErpnextEbaySyncError(
            f'Mode of Payment "{ebay_payment_account}" does not exist!')
    sinv_payments = []
    if cash_on_pickup:
        # Don't create payments, or submit, for Cash On Pickup
        pass
    elif payout_subtotal > 0.0:
        sinv_payments.append({
            "mode_of_payment": ebay_payment_account,
            "default": True,
            "amount": payout_subtotal}
        )
        submit_on_pay = True

    customer_name = order_dict['customer_name']
    cust_email = frappe.get_value('Address', db_address_name, 'email_id')

    if cash_on_pickup:
        title = f"""eBay COD: {customer_name} [{', '.join(sku_list)}]"""
    else:
        title = f"""eBay: {customer_name} [{', '.join(sku_list)}]"""

    sinv_dict = {
        "doctype": "Sales Invoice",
        "naming_series": "SINV-",
        "pos_profile": f"eBay {currency}",
        "title": title,
        "customer": db_cust_name,
        "territory": territory,
        "shipping_address_name": db_address_name,
        "ebay_order_id": ebay_order_id,
        "ebay_site_id": listing_site,
        "ebay_purchase_site_id": purchase_site,
        "buyer_message": buyer_checkout_message,
        "ebay_collect_and_remit": total_collect_and_remit or None,
        "collect_and_remit_details": collect_and_remit_details or None,
        "ebay_max_estimated_delivery_date": min(max_delivery_dts or [None]),
        "ebay_ship_by_date": min(ship_by_dts or [None]),
        "contact_email": cust_email,
        "posting_date": posting_date.date(),
        "posting_time": posting_date.time(),
        "due_date": posting_date,
        "set_posting_time": True,
        "currency": currency,
        "conversion_rate": conversion_rate,
        "ignore_pricing_rule": True,
        "apply_discount_on": "Net Total",
        "status": "Draft",
        "update_stock": True,
        "is_pos": True,
        "taxes": taxes,
        "payments": sinv_payments,
        "items": sinv_items
    }

    sinv = frappe.get_doc(sinv_dict)
    sinv.run_method('erpnext_ebay_before_insert')
    sinv.insert()
    sinv.run_method('erpnext_ebay_after_insert')

    if sinv.outstanding_amount:
        debug_msgprint(
            f'Sales Invoice: {sinv.name} has an outstanding amount!',
            print_func)
    elif submit_on_pay:
        # This is an order which adds up and has an approved payment method
        # Submit immediately
        sinv.submit()

    debug_msgprint(f'Adding Sales Invoice: {ebay_user_id} : {sinv.name}',
                   print_func)
    changes.append({"ebay_change": "Adding Sales Invoice",
                    "ebay_user_id": ebay_user_id,
                    "customer_name": customer_name,
                    "customer": db_cust_name,
                    "address": db_address_name,
                    "ebay_order": ebay_order_id})

    # Commit changes to database
    frappe.db.commit()

    return


def create_return_sales_invoice(order_dict, order, changes, print_func=None):
    """
    If the order has been refunded, Create a Sales Invoice return from
    the eBay order.
    """

    # Check there is a refund.
    if order['order_payment_status'] not in ('FULLY_REFUNDED',
                                             'PARTIALLY_REFUNDED'):
        # If no refund, return now.
        return

    # Find the existing Sales Invoice, and its latest amendment.
    ebay_user_id = order_dict['ebay_user_id']
    ebay_order_id = order_dict['ebay_order_id']
    customer = order_dict['customer']
    customer_name = order_dict['customer_name']
    cancelled_names = []

    sinv_fields = db_get_ebay_doc(
        'Sales Invoice', ebay_order_id, fields=['name', 'docstatus'],
        log=changes, none_ok=True)
    if sinv_fields is None:
        # No SINV, so don't create refund
        return
    while sinv_fields.docstatus != 1:
        if sinv_fields.docstatus == 0:
            # Don't create refund from non-submitted SINV
            return
        cancelled_names.append(sinv_fields.name)
        search = frappe.get_all(
            'Sales Invoice',
            fields=['name', 'docstatus'],
            filters={'amended_from': sinv_fields.name}
        )
        if not search:
            # No amended document
            return
        elif len(search) > 1:
            raise ValueError(f'Multiple amended documents! {sinv_fields.name}')
        sinv_fields = search[0]
    # sinv_fields is now the final SINV
    sinv_name = sinv_fields.name

    # Check for a return to any of the cancelled documents
    for cancelled_name in cancelled_names:
        return_sinvs = frappe.get_all(
            'Sales Invoice',
            fields=['name'],
            filters={'return_against': cancelled_name, 'docstatus': ['!=', 2]}
        )
        if return_sinvs:
            return_names = ', '.join([x.name for x in return_sinvs])
            raise ValueError(
                f'Cancelled {cancelled_name} has return(s) {return_names}!')

    # Check for return from the final SINV
    sinv_ret = frappe.get_all(
        'Sales Invoice',
        fields=['name'],
        filters={'return_against': sinv_name, 'docstatus': ['!=', 2]}
    )
    if sinv_ret:
        return

    # Need to create return SINV - gather info and run checks
    if not order['payment_summary']['refunds']:
        frappe.throw(f'Order {ebay_order_id} missing refund info?',
                     exc=ErpnextEbaySyncError)
    elif len(order['payment_summary']['refunds']) > 1:
        frappe.msgprint(f'Warning: Order {ebay_order_id} has multiple refunds')
    refund = order['payment_summary']['refunds'][0]

    default_currency = get_default_currency()
    ebay_payment_account = f'eBay Managed {default_currency}'
    posting_date = datetime.datetime.strptime(
        refund['refund_date'][:-1] + 'UTC', '%Y-%m-%dT%H:%M:%S.%f%Z')
    if refund['amount']['currency'] != default_currency:
        raise ValueError('Unexpected base refund currency!')

    # Create a return Sales Invoice for the relevant quantities and amount.
    sinv_doc = frappe.get_doc('Sales Invoice', sinv_name)
    return_doc = make_return_doc("Sales Invoice", sinv_name)
    return_doc.update_stock = False
    return_doc.posting_date = posting_date.date()
    return_doc.posting_time = posting_date.time()
    return_doc.due_date = posting_date
    return_doc.set_posting_time = True
    refund_type_str = REFUND_NAME[order['order_payment_status']]
    return_doc.title = f"""eBay {refund_type_str} Refund: {customer_name}"""

    if len(return_doc.payments) != 1:
        raise ValueError('Wrong number of payments!')
    if return_doc.payments[0].mode_of_payment != ebay_payment_account:
        raise ValueError('Wrong mode of payment!')

    if order['order_payment_status'] == 'FULLY_REFUNDED':
        # Fully refunded; just use total from refund SINV
        base_refund_total = return_doc.base_grand_total
    else:
        # Partially refunded only
        # Adjust quantities and rates on return
        exc_rate = return_doc.conversion_rate

        # Identify shipping item on return_doc
        items_by_item_code = {x.item_code: x for x in return_doc.items}
        ship_item = items_by_item_code.get(SHIPPING_ITEM, None)

        # Refund amount from line items
        refund_skus = {}
        if ship_item:
            refund_skus[SHIPPING_ITEM] = 0.0
        non_refund_skus = []
        refund_total = 0.0
        for li in order['line_items']:
            # Get the refund for each SKU, and the total
            if li['refunds']:
                # Consider only the _first_ refund for now
                refund_value = float(li['refunds'][0]['amount']['value'])
                if ship_item:
                    li_ship = float(
                        li['delivery_cost']['shipping_cost']['value']
                    )
                    li_total = float(li['total']['value'])
                    li_ship_refund = refund_value * li_ship / li_total
                    refund_skus[SHIPPING_ITEM] += li_ship_refund
                else:
                    li_ship_refund = 0.0
                refund_skus[li['sku']] = refund_value - li_ship_refund
            else:
                refund_value = 0.0
                non_refund_skus.append(li['sku'])
            refund_total += refund_value

        # Refund amount (after fee credits) from payments section
        refund_payment_amount = refund['amount']
        refund_payment = float(
            refund_payment_amount['converted_from_value']
            or refund_payment_amount['value'])
        base_refund_payment = float(refund_payment_amount['value'])

        # Fee credits are the difference between the refund amounts and
        # the refund payment (which we do not consider further here)
        fee_credit = refund_total - refund_payment
        base_fee_credit = round(fee_credit * exc_rate, 2)

        base_refund_total = round(base_refund_payment + base_fee_credit, 2)

        # Calculate an exchange rate that works
        return_doc.conversion_rate = get_magic_exchange_rate(
            exc_rate, base_refund_total, refund_total)

        # Adjust payment
        return_doc.payments[0].amount = -refund_total

        # Calculate taxes
        tax = (sinv_doc.taxes or [None])[0]

        if not sinv_doc.taxes:
            tax_rate = 0
        elif len(sinv_doc.taxes) != 1:
            frappe.throw(f'Sales invoice {sinv_name} has multiple tax entries!',
                         exc=ErpnextEbaySyncError)
        elif tax.included_in_print_rate:
            frappe.throw(f'Sales invoice {sinv_name} has inclusive tax',
                         exc=ErpnextEbaySyncError)
        elif tax.charge_type != 'Actual':
            frappe.throw(f'Sales invoice {sinv_name} has calculated tax',
                         exc=ErpnextEbaySyncError)
        else:
            # Need to adjust actual taxes
            tax_rate = round(tax.total / (tax.total - tax.tax_amount), 3)

        # Calculate tax amount and adjust taxes
        if tax_rate:
            tax_amount = round(refund_total - (refund_total / tax_rate), 2)
            ex_tax_refund = round(refund_total - tax_amount, 2)
            ret_tax = return_doc.taxes[0]
            ret_tax.charge_type = 'Actual'
            ret_tax.total = -refund_total
            ret_tax.tax_amount = -tax_amount
            # Adjust refund_skus
            tax_frac = ex_tax_refund / refund_total
            for sku in refund_skus:
                refund_skus[sku] *= tax_frac
        else:
            ex_tax_refund = refund_total

        # Get return items in quantity order
        return_items = []
        for it in return_doc.items:
            if it.item_code in non_refund_skus:
                # No refund for this item
                it.qty = 0
                it.rate = 0.0
            else:
                # Add item
                return_items.append(it)
        return_items.sort(key=operator.attrgetter('qty'), reverse=True)

        # Allocate refunds to items
        original_rates = [x.rate for x in return_items]
        for i, item in enumerate(return_items):
            # Note that amount is _negative_, so the 'max' ensures that
            # the refund is not more than the original price
            item.amount = max(
                item.amount, round(-refund_skus[item.item_code], 2)
            )
            item.rate = item.amount / item.qty
        refund_remainder = (
            ex_tax_refund
            - sum(-x.amount for x in return_items)
        )

        for i, item in enumerate(return_items):
            if abs(refund_remainder) < 0.005:
                # Done
                refund_remainder = 0
                break
            if refund_remainder > 0:
                # Must add more refund to item
                possible_refund = (original_rates[i] - item.rate) * -item.qty
                amount_change = min(refund_remainder, possible_refund)
            else:
                # Must remove refund (all quantities negative)
                # max() returns value closer to zero here
                amount_change = max(refund_remainder, item.amount)
            # Note that amount is _negative_, so the 'max' ensures that
            # the refund is not more than the original price
            item.amount = max(
                original_rates[i] * item.qty,
                round(item.amount + amount_change, 2)
            )
            item.rate = item.amount / item.qty

            refund_remainder = (
                ex_tax_refund
                - sum(-x.amount for x in return_items)
            )

        if refund_remainder:
            raise ErpnextEbaySyncError(
                'Refund allocation algorithm insufficiently '
                + f'clever: {ebay_order_id}')

        # Delete items that have zero value or qty
        return_doc.items[:] = [
            x for x in return_doc.items if (x.rate and x.qty)
        ]
        refund_sum = sum(round(x.amount, 2) for x in return_doc.items)
        if abs(refund_sum - -ex_tax_refund) > 0.0001:
            raise ErpnextEbaySyncError('Problem calculating refund rates!')

    for item in return_doc.items:
        item.margin_type = None

    return_doc.run_method('erpnext_ebay_before_insert')
    old_conversion_rate = sinv_doc.conversion_rate
    exc_changed = old_conversion_rate != return_doc.conversion_rate
    if exc_changed:
        # Do a bad thing
        frappe.db.set_value(
            'Sales Invoice', sinv_doc.name, 'conversion_rate',
            return_doc.conversion_rate, update_modified=False)
        # Avoid rounding meaning the exchange rate check is still triggered
        return_doc.conversion_rate = sinv_doc.db_get('conversion_rate')
    return_doc.insert()
    if exc_changed:
        # Fix the bad thing
        frappe.db.set_value(
            'Sales Invoice', sinv_doc.name, 'conversion_rate',
            old_conversion_rate, update_modified=False)

    return_doc.run_method('erpnext_ebay_after_insert')
    #return_doc.submit()

    if CREATE_WARRANTY_CLAIMS:
        # Create a Warranty Claim for the refund, if one does not exist.
        wc_doc = frappe.get_doc({
            'doctype': 'Warranty Claim',
            'status': 'Open',
            'complaint_date': return_doc.posting_date,
            'customer': customer,
            'customer_name': customer_name
        })
        sinv_url = frappe.utils.get_url_to_form('Sales Invoice', sinv_doc.name)
        ret_url = frappe.utils.get_url_to_form('Sales Invoice', return_doc.name)
        sinv_name_html = frappe.utils.escape_html(sinv_doc.name)
        ret_name_html = frappe.utils.escape_html(return_doc.name)
        refund_html = frappe.utils.escape_html(
            frappe.utils.fmt_money(base_refund_total,
                                   currency=default_currency)
        )
        if return_doc.currency == default_currency:
            refund_currency_html = ''
        else:
            cur_str = frappe.utils.fmt_money(return_doc.paid_amount,
                                            currency=return_doc.currency)
            refund_currency_html = frappe.utils.escape_html(f' ({cur_str})')

        wc_doc.complaint = f"""
            <p>eBay {refund_type_str} Refund</p>
            <p>SINV <a href="{sinv_url}">{sinv_name_html}</a>;
                Return SINV <a href="{ret_url}">{ret_name_html}</a></p>
            <p>Refund amount: {refund_html}{refund_currency_html}</p>
            <p>This Warranty Claim has been auto-generated in response
            to a refund on eBay.</p>"""
        wc_doc.insert()

        debug_msgprint(
            f'Adding return Sales Invoice: {ebay_user_id} : {return_doc.name}',
            print_func)
        changes.append({"ebay_change": "Adding return Sales Invoice",
                        "ebay_user_id": ebay_user_id,
                        "customer_name": customer_name,
                        "customer": customer,
                        "address": order_dict['address'],
                        "ebay_order": ebay_order_id})

    # Commit changes to database
    frappe.db.commit()


def get_magic_exchange_rate(rate, home_amount, foreign_amount):
    """If we have an exchange rate, and two amounts converted by
    that exchange rate, find the 'best' exchange rate equal to or
    close to that exchange rate where conversion of those amounts,
    in both directions, gives the other value even when rounding
    to 2dp.

    NOTE - Returns None if no exchange rate can be found.
    """
    max_conversion_rate = min(
        (home_amount+0.00495) / foreign_amount,
        home_amount / (foreign_amount-0.00495)
    )
    min_conversion_rate = max(
        (home_amount-0.00495) / foreign_amount,
        home_amount / (foreign_amount+0.00495)
    )
    if max_conversion_rate < min_conversion_rate:
        return None
    if min_conversion_rate <= rate <= max_conversion_rate:
        # Supplied exchange rate is fine
        return rate
    elif min_conversion_rate > rate:
        # Supplied rate is too low; use minimum conversion rate
        return min_conversion_rate
    else:
        # Supplied rate is too high; use maximum conversion rate
        return max_conversion_rate


def determine_territory(country):
    """Determine correct UK, EU or non-EU territory for Customer."""
    if (not country) or country == 'United Kingdom':
        return 'United Kingdom'

    if country in EU_COUNTRIES:
        return 'EU'

    return 'Rest Of The World'


def determine_income_accounts(country):
    """Determine correct UK, EU or non-EU income accounts."""
    if (not country) or country == 'United Kingdom':
        return (
            f'Sales - {COMPANY_ACRONYM}',
            f'Shipping (Sales) - {COMPANY_ACRONYM}',
            f'Sales Tax UK - {COMPANY_ACRONYM}'
        )

    if country in EU_COUNTRIES:
        return (
            f'Sales EU - {COMPANY_ACRONYM}',
            f'Shipping EU (Sales) - {COMPANY_ACRONYM}',
            f'Sales Tax EU - {COMPANY_ACRONYM}'
        )

    return (
        f'Sales Non-EU - {COMPANY_ACRONYM}',
        f'Shipping Non-EU (Sales) - {COMPANY_ACRONYM}',
        f'Sales Tax Non-EU - {COMPANY_ACRONYM}'
    )


def is_ebay_evtn(address_fragment):
    """Test if the address fragment provided is an eBay VTN."""
    return address_fragment.startswith('ebay') and len(address_fragment) == 11


def sanitize_postcode(in_postcode):
    """Take a UK postcode and tidy it up (spacing and capitals)."""

    postcode = in_postcode.strip().replace(' ', '').upper()
    if (6 > len(postcode) > 8):
        raise ValueError('Unknown postcode type!')

    # A single space always precedes the last three characters of a UK postcode
    postcode = postcode[:-3] + ' ' + postcode[-3:]

    return postcode


def sanitize_country_code(country_code):
    """Attempt to match the input country code with a country.
    Accounts for eBay country code and Frappe country name weirdness.
    """
    if country_code is None:
        return None

    # Special quick case for UK code
    if country_code == 'GB':
        return 'United Kingdom'

    # eBay-only non-ISO codes
    if country_code in ISO_EXTRA_CODES:
        return ISO_EXTRA_CODES[country_code]

    try:
        country_name = countries.get(country_code).name
    except KeyError:
        # Country code not found
        return None

    # Translate to Frappe countries
    if country_name in ISO_COUNTRIES_TO_DB:
        country_name = ISO_COUNTRIES_TO_DB[country_name]
    return country_name


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
        fields=fields_search
    )

    if len(doc_queries) == 1:
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
