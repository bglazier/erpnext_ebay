# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import six

#sys.path.insert(0, "/Users/ben/dev/ebaysdk-python/dist/ebaysdk-2.1.5-py2.7.egg")
#sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/ebaysdk-2.1.4-py2.7.egg")
#sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/lxml-3.6.4-py2.7-linux-i686.egg")

import frappe
from frappe import _

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

PATH_TO_YAML = os.path.join(
    os.sep, frappe.utils.get_bench_path(), 'sites', frappe.get_site_path(), 'ebay.yaml')


def convert_to_unicode(obj):
    """Take an object, and recursively convert strings to unicode.

    FOR PYTHON 2 ONLY
    Opens lists and dictionary items recursively.

    Returns a new/modified string/list/dictionary/nested object as appropriate.
    """

    if isinstance(obj, dict):
        # Dictionary
        for key, value in obj.iteritems():
            obj[key] = convert_to_unicode(value)
        return obj
    elif isinstance(obj, list):
        obj[:] = [convert_to_unicode(x) for x in obj]
        return obj
    elif isinstance(obj, str):
        # Convert string to unicode
        return obj.decode('utf-8')
    elif isinstance(obj, unicode):
        # Already unicode - do nothing.
        pass
    else:
        # Unhandled type
        return obj


def get_orders():
    """Returns a list of recent orders from the Ebay TradingAPI"""

    orders = []
    page = 1
    num_days = frappe.db.get_value(
        'eBay Manager Settings', filters=None, fieldname='ebay_sync_days')

    try:
        if num_days < 1:
            frappe.msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    try:
        # Initialize TradingAPI; default timeout is 20.

        api = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)
        while True:
            # TradingAPI results are paginated, so loop until
            # all pages have been obtained
            api.execute('GetOrders', {'NumberOfDays': num_days,
                                      'Pagination': {'EntriesPerPage': 100,
                                                     'PageNumber': page}})

            orders_api = api.response.dict()

            if int(orders_api['ReturnedOrderCountActual']) > 0:
                orders.extend(orders_api['OrderArray']['Order'])
            if orders_api['HasMoreOrders'] == 'false':
                break
            page += 1

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    if sys.version_info.major == 2:
        # Convert all strings to unicode
        orders = convert_to_unicode(orders)

    return orders, num_days


''''
def get_order_transactions(order_id):
    """get_order_transactions"""

    orders = []

    order_trans = None
    order_trans = []

    try:

        api = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)

        while True:

            api.execute('GetOrderTransactions', {'OrderID': order_id})
            order_trans_api = api.response.dict()

            #if int(order_trans_api['ReturnedOrderCountActual']) > 0:
            orders.extend(order_trans_api['TransactionArray']) #['OrderTransactions'])


    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e


    return order_trans
'''
