"""Functions to read through eBay orders and load customers and addresses."""

from __future__ import unicode_literals
from __future__ import print_function

import datetime

import frappe
from frappe import msgprint,_
from frappe.utils import flt

from ebay_requests import get_orders

# Option to use eBay shipping address name as customer name.
# eBay does not normally provide buyer name.
# Don't say you weren't warned...
assume_shipping_name_is_ebay_name = True

@frappe.whitelist()
def sync():
    """Sync the Ebay database with the Frappe database."""

    # Load orders from Ebay
    orders, num_days = get_orders()

    # Create a synchronization log
    log_dict = {"doctype": "eBay sync log",
                "ebay_sync_datetime": datetime.datetime.now(),
                "ebay_sync_days": num_days,
                "ebay_log_table": []}
    changes = []

    try:
        # Load new customers
        for order in orders:
            cust_details, address_details = extract_customer(order)
            create_customer(cust_details, address_details, changes)

        for order in orders:
            order_details = extract_order_info(order, changes)
            create_ebay_order(order_details, changes)

    finally:
        # Save the log, regardless of how far we got
        for change in changes:
            log_dict['ebay_log_table'].append(change)
        log = frappe.get_doc(log_dict)
        log.insert()
        frappe.db.commit()


def extract_customer(order):
    """Process an order, and extract limited customer information.

    order - a single order entry from the eBay TradingAPI.

    Returns a tuple of two dictionarys.
    The first dictionary is ready to create a Customer Doctype entry.
    The second dictionary is ready to create an Address Doctype entry.
    The second dictionary could be replaced by None if there is no address.
    """

    ebay_user_id = order['BuyerUserID']

    has_shipping_address = order['ShippingAddress']['Name'] is not None

    if has_shipping_address:
        shipping_name = order['ShippingAddress']['Name']
        # Tidy up ShippingAddress name, if entirely lower/upper case and not
        # a single word
        if ((shipping_name.islower() or shipping_name.isupper()) and
                ' ' in shipping_name):
            shipping_name = shipping_name.title()

    if has_shipping_address and assume_shipping_name_is_ebay_name:
        customer_name = shipping_name
    else:
        customer_name = ebay_user_id

    customer_dict = {
        "doctype": "Customer",
        "customer_name" : customer_name,
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
        postcode = order['ShippingAddress']['PostalCode']
        address_line1 = order['ShippingAddress']['Street1']
        address_line2 = order['ShippingAddress']['Street2']
        country = order['ShippingAddress']['CountryName']
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

        if postcode is not None and country=='United Kingdom':
            postcode = sanitize_postcode(postcode)
        address_dict = {
            "doctype": "Address",
            "address_title": shipping_name,
            "ebay_address_id": order['ShippingAddress']['AddressID'],
            "address_type": _("Shipping"),
            "address_line1": address_line1,
            "address_line2": address_line2,
            "city": order['ShippingAddress']['CityName'],
            "state": order['ShippingAddress']['StateOrProvince'],
            "pincode": postcode,
            "country": country,
            "phone": order['ShippingAddress']['Phone'],
            "email_id": email_id,
            "customer_name": customer_name}
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
    cust_fields = db_get_ebay_cust(
        ebay_user_id, fields=["name", "customer_name"],
        log=changes, none_ok=False)

    # Get address information, if available
    if 'AddressID' in order['ShippingAddress']:
        ebay_address_id = order['ShippingAddress']['AddressID']

        db_address_name = db_get_ebay_address(
            ebay_address_id, fields=["name"],
            log=changes, none_ok=False)["name"]
    else:
        ebay_address_id = None
        db_address_name = None

    order_dict = {"doctype": "eBay order",
                  "name": order['OrderID'],
                  "ebay_order_id": order['OrderID'],
                  "ebay_user_id": order['BuyerUserID'],
                  "ebay_address_id": ebay_address_id,
                  "customer": cust_fields["name"],
                  "customer_name": cust_fields["customer_name"],
                  "address": db_address_name}

    return order_dict


def create_customer(customer_dict, address_dict, changes=None):
    """Process an order and add the customer; add customer address.
    Does not duplicate entries where possible.

    customer_dict - A dictionary ready to create a Customer doctype.
    address_dict - A dictionary ready to create an Address doctype (or None).
    changes - A sync log list to append to.

    Returns a list of dictionaries for eBay sync log entries."""

    if changes is None:
        changes = []

    updated_db = False

    # First test if the customer already exists
    db_cust_name = None
    ebay_user_id = customer_dict['ebay_user_id']
    if address_dict is not None:
        ebay_address_id = address_dict['ebay_address_id']

    cust_fields = db_get_ebay_cust(
        ebay_user_id, fields=["name", "customer_name"],
        log=changes, none_ok=True)

    if cust_fields is None:
        # We don't have a customer with a matching ebay_user_id
        matched_non_eBay = False

        # If we also have an address, check if we have a
        # matching postcode and name
        if address_dict is not None:
            address_queries = frappe.db.get_all(
                "Address",
                filters={"pincode": address_dict['pincode']},
                fields=["name", "customer"])
            if len(address_queries) == 1:
                # We have a matching postcode - match the name
                db_address_test = address_queries[0]["name"]
                db_cust_name_test = address_queries[0]["customer"]
                cust_queries_test = frappe.db.get_values(
                    "Customer",
                    filters={"name": db_cust_name_test},
                    fieldname="customer_name")
                if len(cust_queries_test) == 1:
                    db_cust_customer_name_test = cust_queries_test[0][0]
                    if (address_dict['customer_name'] ==
                            db_cust_customer_name_test):
                        # We have matched name and postcode
                        matched_non_eBay = True
                        cust_doc = frappe.get_doc("Customer", db_cust_name_test)
                        cust_doc.ebay_user_id = ebay_user_id
                        cust_doc.save()
                        updated_db = True
                        db_cust_name = db_cust_name_test
                        db_cust_customer_name = db_cust_customer_name_test
                        msgprint('Located non-eBay user: ' +
                                 ebay_user_id + ' : ' +
                                 db_cust_customer_name_test)
                        changes.append({"ebay_change": "Located non-eBay user",
                                       "ebay_user_id": ebay_user_id,
                                       "customer_name": db_cust_customer_name,
                                       "customer": db_cust_name,
                                       "address": db_address_test,
                                       "ebay_order": None})

        if not matched_non_eBay:
            msgprint('Adding a user: ' + ebay_user_id +
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
        msgprint('User already exists: ' + ebay_user_id +
                 ' : ' + db_cust_customer_name)
        changes.append({"ebay_change": "User already exists",
                       "ebay_user_id": ebay_user_id,
                       "customer_name": db_cust_customer_name,
                       "customer": db_cust_name,
                       "address": None,
                       "ebay_order": None})

    # Add customer if required
    if db_cust_name is None:
        frappe.get_doc(customer_dict).insert()
        updated_db = True

    if address_dict is None:
        add_address = False
    else:
        address_fields = db_get_ebay_address(
            ebay_address_id, fields=["name"], log=changes, none_ok=True)

        if address_fields is None:
            # Address does not exist; add address
            add_address = True
            db_address_name = None
        else:
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
                address_doc.save()
                updated_db = True

        # Check that customer has a name, not just an eBay user id
        # If not, update with new name if assume_shipping_name_is_ebay_name
        if (db_cust_name is not None) and (assume_shipping_name_is_ebay_name):
            if db_cust_customer_name == ebay_user_id:
                customer_doc = frappe.get_doc("Customer", db_cust_name)
                customer_doc.customer_name = address_dict["customer_name"]
                customer_doc.save()
                msgprint('Updated name: ' + ebay_user_id + ' -> ' +
                         address_dict["customer_name"])
                changes.append({"ebay_change": "Updated name",
                               "ebay_user_id": ebay_user_id,
                               "customer_name": address_dict["customer_name"],
                               "customer": db_cust_name,
                               "address": db_address_name,
                               "ebay_order": None})
                updated_db = True

    # Add address if required
    if add_address:
        if db_cust_name is None:
            # Find new customer 'name' field
            db_cust_name = db_get_ebay_cust(
                ebay_user_id, fields=["name"],
                log=changes, none_ok=False)["name"]
        address_dict['customer'] = db_cust_name
        frappe.get_doc(address_dict).insert()
        updated_db = True

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return None


def create_ebay_order(order_dict, changes):
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
    ebay_address_id = order_dict['ebay_address_id']

    order_fields = db_get_ebay_order(
        ebay_order_id, fields=["name"], log=changes, none_ok=True)

    if order_fields is None:
        # Order does not exist, create eBay order
        db_cust_name = order_dict['customer']
        db_cust_customer_name = order_dict['customer_name']
        db_address_name = order_dict['address']

        cust_queries = frappe.db.get_all(
            "Customer",
            filters={'ebay_user_id': ebay_user_id},
            fields=['name', 'customer_name'])

        cust_fields = db_get_ebay_cust(
            ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)

        db_cust_name = cust_fields['name']
        db_cust_customer_name = cust_fields['customer_name']

        frappe.get_doc(order_dict).insert()
        msgprint('Adding eBay order: ' + ebay_user_id + ' : ' +
                 ebay_order_id)
        changes.append({"ebay_change": "Adding eBay order",
                       "ebay_user_id": ebay_user_id,
                       "customer_name": db_cust_customer_name,
                       "customer": db_cust_name,
                       "address": db_address_name,
                       "ebay_order": ebay_order_id})
        updated_db = True

    else:
        # Order already exists
        # TODO Check if status of order has changed, and if so update??
        # TODO - Should probably check correct customer is linked
        db_order_name = order_fields["name"]
        cust_fields = db_get_ebay_cust(
            ebay_user_id, fields=["name", "customer_name"],
            log=changes, none_ok=False)
        msgprint('eBay order already exists: ' + ebay_user_id + ' : ' +
                 ebay_order_id)
        changes.append({"ebay_change": "eBay order already exists",
                       "ebay_user_id": ebay_user_id,
                       "customer_name": cust_fields["customer_name"],
                       "customer": cust_fields["name"],
                       "address": None,
                       "ebay_order": db_order_name})

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return None


def sanitize_postcode(in_postcode):
    """Take a UK postcode and tidy it up (spacing and capitals)."""

    postcode = in_postcode.strip().replace(' ', '').upper()
    if (6 > len(postcode) > 8):
        print(in_postcode)
        raise ValueError('Unknown postcode type!')
        return in_postcode

    # A single space always precedes the last three characters of a UK postcode
    postcode = postcode[:-3] + ' ' + postcode[-3:]

    return postcode


def sync_error(changes, error_item, error_message,
               ebay_user_id=None, customer_name=None, customer=None,
               address=None, ebay_order=None):
    """Print an error encountered during synchronization.

    Print an error message and item to the console. Log the error message
    to the change log. Throw a frappe error with the error message."""
    print(error_message)
    print(error_item)
    changes.append({"ebay_change": error_message,
                   "ebay_user_id": ebay_user_id,
                   "customer_name": customer_name,
                   "customer": customer,
                   "address": address,
                   "ebay_order": ebay_order})
    msgprint(error_message)
    raise ValueError(error_message)
    #frappe.throw(error_message)  # doesn't produce traceback


def db_get_ebay_cust(ebay_user_id, fields=None, log=None, none_ok=True):
    """Shorthand function for db_get_ebay_doc for Customer"""

    return db_get_ebay_doc("Customer", "ebay_user_id", ebay_user_id,
                           fields, log, none_ok)


def db_get_ebay_address(ebay_address_id, fields=None, log=None, none_ok=True):
    """Shorthand function for db_get_ebay_doc for Address"""

    return db_get_ebay_doc("Address", "ebay_address_id", ebay_address_id,
                           fields, log, none_ok)


def db_get_ebay_order(ebay_order_id, fields=None, log=None, none_ok=True):
    """Shorthand function for db_get_ebay_doc for eBay order"""

    return db_get_ebay_doc("eBay order", "ebay_order_id", ebay_order_id,
                           fields, log, none_ok)


def db_get_ebay_doc(doctype, ebay_id_name, ebay_id,
                    fields=None, log=None, none_ok=True):
    """Get document with matching ebay_id from database.

    Search in the database for document with matching ebay_id_name = ebay_id.
    If fields is None, get the document and return as_dict().
    If fields is not None, return the dict of fields for that for that document.

    If more than one customer found raise an error.
    If no customers found and none_ok is False raise an error, else
    return None.
    """

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
            sync_error(
                log, doc_queries, error_message, customer_name=errstring)

    return retval
