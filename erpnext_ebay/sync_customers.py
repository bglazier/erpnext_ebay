"""Functions to read through eBay orders and load customers and addresses"""

from __future__ import unicode_literals
import frappe
from frappe import msgprint,_
from frappe.utils import flt

from ebay_requests import get_orders


@frappe.whitelist()
def sync_new():
    """Sync the Ebay database with the Frappe database."""

    # Load orders from Ebay and load new customers
    orders = get_orders()
    for order in orders:
        cust, address = extract_customer(order)
        create_customer(cust, address)


def extract_customer(order):
    """Process and order, and extract limited customer information

    order - a single order entry from the eBay TradingAPI

    Returns a tuple of two dictionarys.
    The first dictionary is ready to create a Customer Doctype entry
    The second dictionary is ready to create an Address Doctype entry
    The second dictionary could be replaced by None if there is no address
    """

    ebay_user_id = order['BuyerUserID']

    has_shipping_address = order['ShippingAddress']['Name'] is not None

    if has_shipping_address:
        ShippingAddress_Name = order['ShippingAddress']['Name'].decode("utf-8")
        customer_name = ShippingAddress_Name
    else:
        ShippingAddress_Name = 'None'
        customer_name = ebay_user_id

    if has_shipping_address:
        # Tidy up customer name, if entirely lower/upper case and not
        # a single word (and if not an Ebay username)
        if ((customer_name.islower() or customer_name.isupper()) and
                ' ' in customer_name):
            customer_name = customer_name.title()

    customer_dict = {
        "doctype": "Customer",
        "customer_name" : customer_name,
        "ebay_user_id": ebay_user_id,
        "customer_group": _("Individual"),
        "territory": _("All Territories"),
        "customer_type": _("Individual")}

    if has_shipping_address:
        transactions = order['TransactionArray']['Transaction']
        if len(transactions) == 1:
            email_id = transactions[0]['Buyer']['Email']
        else:
            email_id = None
        if email_id == 'Invalid Request':
            email_id = None
        postcode = order['ShippingAddress']['PostalCode']
        country = order['ShippingAddress']['CountryName']
        if postcode is not None and country=='United Kingdom':
            postcode = sanitize_postcode(postcode)
        address_dict = {"doctype": "Address",
                        "address_title": customer_name,
                        "address_type": _("Shipping"),
                        "address_line1": order['ShippingAddress']['Street1'],
                        "address_line2": order['ShippingAddress']['Street2'],
                        "city": order['ShippingAddress']['CityName'],
                        "state": order['ShippingAddress']['StateOrProvince'],
                        "pincode": postcode,
                        "country": order['ShippingAddress']['CountryName'],
                        "phone": order['ShippingAddress']['Phone'],
                        "email_id": email_id,
                        "is_primary_address": 1,
                        "customer_name": customer_name}
    else:
        address_dict = None

    return customer_dict, address_dict


def create_customer(customer_dict, address_dict):
    """Process an order and add the customer; add customer address
    Does not duplicate entries where possible

    customer_dict - A dictionary ready to create a Customer doctype
    address_dict - A dictionary ready to create an Address doctype (or None)"""

    updated_db = False

    # First test if the customer already exists
    db_cust_name = None
    ebay_user_id = customer_dict['ebay_user_id']

    cust_queries = frappe.db.get_all(
        "Customer",
        filters={"ebay_user_id": ebay_user_id},
        fields=["name", "customer_name"])

    if len(cust_queries) == 0:
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
                                 db_cust_customer_name_test + ' : ' +
                                 ebay_user_id)

        if not matched_non_eBay:
            msgprint('Adding a user: ' + ebay_user_id +
                     ' : ' + customer_dict['customer_name'])
    elif len(cust_queries) == 1:
        # We have a customer with a matching ebay_user_id
        db_cust_name = cust_queries[0]['name']
        db_cust_customer_name = cust_queries[0]['customer_name']
        msgprint('User already exists: ' + ebay_user_id +
                 ' : ' + db_cust_customer_name)
    else:
        # We have multiple customers with this ebay_user_id
        # This is not permitted
        print cust_queries
        frappe.throw('Multiple customer entries with same eBay ID!')

    # Add customer if required
    if db_cust_name is None:
        frappe.get_doc(customer_dict).insert()
        updated_db = True

    if address_dict is None:
        add_address = False
    else:
        # Test if the address already exists
        keys = ('address_line1', 'address_line2', 'city', 'pincode')
        filters = {}
        for key in keys:
            if address_dict[key] is not None:
                filters[key] = address_dict[key]
        
        db_address_name = frappe.db.get_value("Address",
                                              filters=filters,
                                              fieldname="name")
        add_address = db_address_name is None

        # Check that customer has a name, not just an eBay user id
        # If not, update with new name
        if db_cust_name is not None:
            if db_cust_customer_name == ebay_user_id:
                msgprint('Updating name: ' + ebay_user_id + ' -> ' +
                         address_dict["customer_name"])
                cust = frappe.get_doc("Customer", db_cust_name)
                cust.customer_name = address_dict["customer_name"]
                cust.save()
                updated_db = True

    # Add address if required
    if add_address:
        if db_cust_name is None:
            # Find new customer 'name' field
            db_cust_name = frappe.db.get_value(
                "Customer",
                filters={"ebay_user_id": ebay_user_id},
                fieldname="name")
        address_dict['customer'] = db_cust_name
        frappe.get_doc(address_dict).insert()
        updated_db = True

    # Commit changes to database
    if updated_db:
        frappe.db.commit()

    return None


def sanitize_postcode(in_postcode):
    """Take a UK postcode and tidy it up (spacing and capitals)"""

    postcode = in_postcode.strip().replace(' ', '').upper()
    if (6 > len(postcode) > 8):
        print(in_postcode)
        raise ValueError('Unknown postcode type!')
        return in_postcode

    # A single space always precedes the last three characters of a UK postcode
    postcode = postcode[:-3] + ' ' + postcode[-3:]

    return postcode
