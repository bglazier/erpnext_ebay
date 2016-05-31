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
        create_customer(cust, address, no_duplicates=True)


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


def create_customer(customer_dict, address_dict, no_duplicates=True):
    """Process an order and add the customer; add customer address

    customer_dict - A dictionary ready to create a Customer doctype
    address_dict - A dictionary ready to create an Address doctype (or None)
    no_duplicates - Don't duplicate existing entries"""

    # First test if the customer already exists
    db_cust_name = None
    if no_duplicates:
        ebay_user_id = customer_dict['ebay_user_id']

        db_cust_name = frappe.db.get_value(
            "Customer",
            filters={"ebay_user_id": ebay_user_id},
            fieldname="name")
        if db_cust_name is None:
            msgprint('Adding a user: ' + ebay_user_id + ' : ' + customer_dict['customer_name'])
        else:
            msgprint('Not adding a user: ' + ebay_user_id + ' : ' + db_cust_name)

        add_customer = db_cust_name is None
    else:
        add_customer = True

    # Add customer if required
    if add_customer:
        frappe.get_doc(customer_dict).insert()
    
    # Now test if the address already exists
    if address_dict is None:
        add_address = False
    elif no_duplicates:
        keys = ('address_line1', 'address_line2', 'city', 'pincode')
        filters = {}
        for key in keys:
            if address_dict[key] is not None:
                filters[key] = address_dict[key]
        
        db_address_name = frappe.db.get_value("Address",
                                              filters=filters,
                                              fieldname="name")
        add_address = db_address_name is None
    else:
        add_address = True

    # Add address if required
    if add_address:
        if db_cust_name is None:
            # Find new customer 'name' field
            ebay_user_id = customer_dict['ebay_user_id']

            db_cust_name = frappe.db.get_value(
                "Customer",
                filters={"ebay_user_id": ebay_user_id},
                fieldname="name")
        address_dict['customer'] = db_cust_name
        frappe.get_doc(address_dict).insert()

    # Commit changes to database
    if add_customer or add_address:
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
