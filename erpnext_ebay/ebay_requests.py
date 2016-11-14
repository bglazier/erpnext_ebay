"""Functions to retrieve data from eBay via ebaysdk module and TradingAPI"""

from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
#import datetime

sys.path.insert(0, "/home/frappe/")


import frappe
from frappe import _

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


def get_orders():
    """Returns a list of recent orders from the Ebay TradingAPI"""

    orders = None
    ebay_customers = []

    #CreateTimeFrom = str(datetime.date.today())
    #CreateTimeFrom = CreateTimeFrom+'T0:0:0.000Z'
    #CreateTimeTo = str(datetime.datetime.now())
    #CreateTimeTo = CreateTimeTo[0:len(CreateTimeTo)-3]+'Z'

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
        api = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
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

    return orders, num_days


def get_order_transactions(order_id):
    
    order_trans = None
    order_trans = []
    
    try:
        
        api = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
        
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
    