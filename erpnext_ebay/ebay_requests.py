"""Functions to retrieve data from eBay via ebaysdk module and TradingAPI"""

from __future__ import unicode_literals
import os
import sys
#import datetime

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
    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(config_file='ebay.yaml', warnings=True, timeout=20)
        while True:
            # TradingAPI results are paginated, so loop until
            # all pages have been obtained
            api.execute('GetOrders', {'NumberOfDays': 30,
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

    return orders
