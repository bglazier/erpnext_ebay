"""Functions to retrieve data from eBay via ebaysdk module and TradingAPI."""

from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import operator

import frappe
from frappe import _, msgprint

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


siteid = 3  # eBay site id: 0=US, 3=UK


def get_orders():
    """Returns a list of recent orders from the Ebay TradingAPI."""

    orders = None
    ebay_customers = []

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

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    while True:
        # TradingAPI results are paginated, so loop until
        # all pages have been obtained
        try:
            api.execute('GetOrders', {'NumberOfDays': num_days,
                                      'Pagination': {'EntriesPerPage': 100,
                                                     'PageNumber': page}})
        except ConnectionError as e:
            print(e)
            print(e.response.dict())
            raise e

        orders_api = api.response.dict()

        if int(orders_api['ReturnedOrderCountActual']) > 0:
            orders.extend(orders_api['OrderArray']['Order'])
        if orders_api['HasMoreOrders'] == 'false':
            break
        page += 1

    return orders, num_days


def get_categories_versions():
    """Load the version number of the current eBay categories
    and category features.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=20)

        response1 = api.execute('GetCategories', {'LevelLimit': 1,
                                                  'ViewAllNodes': False})

        response2 = api.execute('GetCategoryFeatures', {})

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    categories_version = response1.reply.CategoryVersion
    features_version = response2.reply.CategoryVersion

    return (categories_version, features_version)


def get_categories():
    """Load the eBay categories for the categories cache."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=60)

        response = api.execute('GetCategories', {'DetailLevel': 'ReturnAll',
                                                 'ViewAllNodes': True})

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    categories_data = response.dict()

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
    return categories_data, max_level


def get_features(categories_data):
    """Load the eBay category features for the features cache."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=60)

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    features_data = None

    problematic_categories = ['1']
    # Loop over each top-level category, pulling in all of the data
    for category in categories_data['TopLevel']:
        category_id = category['CategoryID']
        # print('Loading for category {}...'.format(category_id))

        # BEGIN DUBIOUS WORKAROUND
        if category_id in problematic_categories:
            # Loop over this category's children instead
            for category_child in category['Children']:
                category_child_id = category_child['CategoryID']
                # print('Loading for subcategory {}...'.format(
                #       category_child_id))

                try:
                    response = api.execute('GetCategoryFeatures',
                                           {'CategoryID': category_child_id,
                                            'DetailLevel': 'ReturnAll',
                                            'ViewAllNodes': True})
                except ConnectionError as e:
                    print(e)
                    print(e.response.dict())
                    raise e
                response_dict = response.dict()
                if features_data is None:
                    features_data = response_dict
                else:
                    features_data['Category'].extend(response_dict['Category'])
        # END DUBIOUS WORKAROUND
        else:
            try:
                response = api.execute('GetCategoryFeatures',
                                       {'CategoryID': category_id,
                                        'DetailLevel': 'ReturnAll',
                                        'ViewAllNodes': True})
            except ConnectionError as e:
                print(e)
                print(e.response.dict())
                raise e
            response_dict = response.dict()
        # print('done.')

        if features_data is None:
            # First batch of new categories
            features_data = response_dict
        else:
            # Just add new categories
            features_data['Category'].extend(response_dict['Category'])

    # Extract the new version number
    features_version = features_data['CategoryVersion']

    # Return the new features
    return features_version, features_data


@frappe.whitelist()
def GeteBayDetails():
    """Perform a GeteBayDetails call and save the output in geteBayDetails.txt
    in the site root directory
    """
    filename = os.path.join(frappe.utils.get_site_path(),
                            'GeteBayDetails.txt')

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=20)

        response = api.execute('GeteBayDetails', {})

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    with open(filename, 'wt') as f:
        f.write(repr(response.dict()))

    return None


def verify_add_item(listing_dict):
    """Perform a VerifyAddItem call, and return useful information"""

    try:
        api = Trading(domain='api.sandbox.ebay.com', config_file='ebay.yaml',
                      siteid=siteid, warnings=True, timeout=20)

        response = api.execute('VerifyAddItem', listing_dict)

    except ConnectionError as e:
        # traverse the DOM to look for error codes
        for node in api.response.dom().findall('ErrorCode'):
            msgprint("error code: %s" % node.text)

        # check for invalid data - error code 37
        if 37 in api.response_codes():
            if 'Errors' in api.response.dict():
                errors_dict = api.response.dict()['Errors']
                errors_list = []
                for key, value in errors_dict.items():
                    errors_list.append('{} : {}'.format(key, value))
                msgprint('\n'.join(errors_list))
                if 'ErrorParameters' in errors_dict:
                    parameter = errors_dict['ErrorParameters']['Value']
                    parameter_stack = parameter.split('.')
                    parameter_value = listing_dict
                    for stack_entry in parameter_stack:
                        parameter_value = parameter_value[stack_entry]
                    msgprint("'{}': '{}'".format(parameter, parameter_value))

        else:
            msgprint("Unknown error: {}".format(api.response_codes()))
            msgprint('{}'.format(e))
            msgprint('{}'.format(e.response.dict()))
        return {'ok': False}

    # Success?
    ok = True
    ret_dict = {'ok': ok}

    msgprint(response.dict())

    return ret_dict
