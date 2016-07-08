"""Functions to retrieve data from eBay via ebaysdk module and TradingAPI"""

from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import operator

import frappe
from frappe import _, msgprint

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


siteid = 3 # eBay site id: 0=US, 3=UK


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
            msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(config_file='ebay.yaml', siteid=siteid,
                      warnings=True, timeout=20)
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


def get_categories_version():
    """Load the version number of the current eBay categories"""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=20)

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    response = api.execute('GetCategories', {'LevelLimit': 1,
                                             'ViewAllNodes': False})

    return response.dict()['Version']


def get_categories():
    """Load the eBay categories into the categories cache"""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=20)

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    response = api.execute('GetCategories', {'DetailLevel': 'ReturnAll',
                                             'ViewAllNodes': True})

    categories_data = response.dict()

    # Extract the new version number
    categories_version = int(categories_data['Version'])
    del categories_data['Version']

    # Process the remaining categories data
    cl = categories_data['CategoryArray']['Category']
    # Use one dictionary element per level, to store each Category against its
    # CategoryID. For simplicity don't use the first [0] level as CategoryLevel
    # is one-indexed.
    levels = []
    for cat in cl:
        cat['Children'] = []
        cat_level = int(cat['CategoryLevel'])
        while cat_level > len(levels)-1:
            levels.append({})
        # Add the category to the relevant level dictionary
        levels[cat_level][cat['CategoryID']] = cat

    max_level = len(levels) - 1

    # Loop over all deeper levels; connect categories to their parents
    for parent_level, level_dict in enumerate(levels[2:], start=1):
        for cat in level_dict.values():
            parent = levels[parent_level][cat['CategoryParentID']]
            parent['Children'].append(cat)

    # Sort the Children list of each category according to its CategoryName
    for cat in cl:
        cat['Children'].sort(key=operator.itemgetter('CategoryName'))

    # Sort the top level list according to the CategoryName of the categories
    top_level = levels[1].values()
    top_level.sort(key=operator.itemgetter('CategoryName'))

    categories_data['TopLevel'] = top_level

    del categories_data['CategoryArray']

    # Return the new categories
    return categories_version, categories_data, max_level


def sandbox_listing_testing():

    pass

















