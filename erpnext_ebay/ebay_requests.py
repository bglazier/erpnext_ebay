# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import six
import operator

if six.PY2:
    from collections import Sequence
else:
    from collections.abc import Sequence

import frappe
from frappe import _, msgprint

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

PATH_TO_YAML = os.path.join(
    os.sep, frappe.utils.get_bench_path(), 'sites', frappe.get_site_path(), 'ebay.yaml')

default_site_id = 3  # eBay site id: 0=US, 3=UK


def handle_ebay_error(e):
    """Throw an appropriate Frappe error message on error."""
    try:
        api_dict = e.response.dict()
        if isinstance(api_dict['Errors'], Sequence):
            errors = api_dict['Errors']
        else:
            errors = [api_dict['Errors']]
        messages = []
        for error in errors:
            if error['ErrorCode'] == "932":
                # eBay auth token has expired
                messages.append('eBay API token has expired:\n"{}"'.format(
                    error['LongMessage']))
            else:
                # Some other eBay error
                messages.append('eBay error:\n"{}"'.format(
                    error['LongMessage']))
        frappe.throw('\n'.join(messages))
    except Exception:
        # We have not handled this correctly; just raise the original error.
        raise e


def test_for_message(api_dict):
    """Test for error/warning messages."""

    # First check for expiring Auth token.
    if 'HardExpirationWarning' in api_dict:
        message = ('WARNING - eBay auth token will expire within 7 days!\n'
                   + 'Expiry date/time: ' + api_dict['HardExpirationWarning'])
        msgprint(message)
        print(message)
    # Now check for errors/warnings.
    if 'Errors' not in api_dict:
        return
    if isinstance(api_dict['Errors'], Sequence):
        errors = api_dict['Errors']
    else:
        errors = [api_dict['Errors']]
    messages = []
    for error in errors:
        messages.append('{} code {}: {}'.format(
            error['SeverityCode'], error['ErrorCode'], error['LongMessage']))
    msgprint('\n'.join(messages))
    print('\n'.join(messages))


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
        return obj
    else:
        # Unhandled type
        return obj


def get_orders(site_id=default_site_id):
    """Returns a list of recent orders from the eBay TradingAPI"""

    num_days = frappe.db.get_value(
        'eBay Manager Settings', filters=None, fieldname='ebay_sync_days')

    try:
        if num_days < 1:
            frappe.msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    orders = []
    page = 1

    try:
        # Initialize TradingAPI; default timeout is 20.

        api = Trading(config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=20)
        while True:
            # TradingAPI results are paginated, so loop until
            # all pages have been obtained
            api.execute('Get Orders', {
                'NumberOfDays': num_days,
                'Pagination': {
                    'EntriesPerPage': 50,
                    'PageNumber': page}
                })

            orders_api = api.response.dict()
            test_for_message(orders_api)

            if int(orders_api['ReturnedOrderCountActual']) > 0:
                orders.extend(orders_api['OrderArray']['Order'])
            if orders_api['HasMoreOrders'] == 'false':
                break
            page += 1

    except ConnectionError as e:
        handle_ebay_error(e)

    if six.PY2:
        # Convert all strings to unicode
        orders = convert_to_unicode(orders)

    return orders, num_days


def get_listings(listings_type='Summary', api_options=None,
                 api_inner_options=None, site_id=default_site_id):
    """Returns a list of listings from the eBay TradingAPI."""

    INNER_PAGINATE = ('ActiveList', 'ScheduledList', 'SoldList', 'UnsoldList')
    RESPONSE_FIELDS = {
        'ActiveList': ('ItemArray', 'Item'),
        'DeletedFromSoldList': ('OrderTransactionArray', 'OrderTransaction'),
        'DeletedFromUnsoldList': ('ItemArray', 'Item'),
        'ScheduledList': ('ItemArray', 'Item'),
        'SellingSummary': ('SellingSummary', None),
        'SoldList': ('OrderTransactionArray', 'OrderTransaction'),
        'UnsoldList': ('ItemArray', 'Item'),
        'Summary': (None, None)}

    if api_options and listings_type in api_options:
        raise ValueError('Set listing type and inner options separately!')

    listings = []
    page = 1
    n_pages = None

    if api_options is None:
        api_options = {}

    if api_inner_options is None:
        api_inner_options = {}

    if listings_type != 'Summary':
        # Summary is not a real option, just a placeholder to get summary
        # information.
        api_inner_options['Include'] = True

        api_options[listings_type] = api_inner_options

    try:
        # Initialize TradingAPI; default timeout is 20.

        api = Trading(config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=20)
        while True:
            # TradingAPI results are often paginated, so loop until
            # all pages have been obtained
            if listings_type in INNER_PAGINATE:
                api_options[listings_type]['Pagination'] = {
                    'EntriesPerPage': 50, 'PageNumber': page}

            api.execute('GetMyeBaySelling', api_options)

            listings_api = api.response.dict()
            test_for_message(listings_api)

            # If appropriate on our first time around, find the total
            # number of pages.
            if n_pages is None:
                # Get Summary if it exists
                if 'Summary' in listings_api:
                    summary = listings_api['Summary']
                else:
                    summary = None
                if listings_type in INNER_PAGINATE:
                    n_pages = int(
                        (listings_api[listings_type]
                         ['PaginationResult']['TotalNumberOfPages']))
                print('n_pages = ', n_pages)
            print('page {} / {}'.format(page, n_pages))

            # Locate the appropriate results
            field, array = RESPONSE_FIELDS[listings_type]
            if field is None:
                listings = listings_api
            elif array is None:
                listings = (
                    listings_api[field] if field in listings_api else None)
            else:
                listings.extend(listings_api[listings_type][field][array])

            # If we are on the last page or there are no pages, break.
            if page >= (n_pages or 0):
                break
            page += 1

    except ConnectionError as e:
        handle_ebay_error(e)

    if six.PY2:
        # Convert all strings to unicode
        listings = convert_to_unicode(listings)

    return listings, summary


def get_categories_versions(site_id=default_site_id):
    """Load the version number of the current eBay categories
    and category features.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=20)

        response1 = api.execute('GetCategories', {'LevelLimit': 1,
                                                  'ViewAllNodes': False})
        test_for_message(response1.response.dict())

        response2 = api.execute('GetCategoryFeatures', {})
        test_for_message(response2.response.dict())

    except ConnectionError as e:
        handle_ebay_error(e)

    categories_version = response1.reply.CategoryVersion
    features_version = response2.reply.CategoryVersion

    return (categories_version, features_version)


def get_categories(site_id=default_site_id):
    """Load the eBay categories for the categories cache."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=60)

        response = api.execute('GetCategories', {'DetailLevel': 'ReturnAll',
                                                 'ViewAllNodes': 'true'})

    except ConnectionError as e:
        handle_ebay_error(e)

    categories_data = response.dict()

    if six.PY2:
        # Convert all strings to unicode
        categories_data = convert_to_unicode(categories_data)

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


def get_features(site_id=default_site_id):
    """Load the eBay category features for the features cache."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=60)

    except ConnectionError as e:
        handle_ebay_error(e)

    features_data = None
    feature_definitions = set()
    listing_durations = {}

    # Loop over each top-level category, pulling in all of the data
    search_categories = frappe.db.sql("""
        SELECT CategoryID, CategoryName, CategoryLevel
            FROM eBay_categories_hierarchy WHERE CategoryParentID=0
        """, as_dict=True)

    # BEGIN DUBIOUS WORKAROUND
    # Even some top-level categories have a habit of timing out
    # Run over their subcategories instead
    problematic_categories = ['1']  # Categories that timeout
    problem_parents = []
    problem_children = []
    for category in search_categories:
        category_id = category['CategoryID']
        if category_id in problematic_categories:
            problem_parents.append(category)
            children = frappe.db.sql("""
                SELECT CategoryID, CategoryName, CategoryLevel
                FROM eBay_categories_hierarchy WHERE CategoryParentID=%s
                """, (category_id,), as_dict=True)
            problem_children.extend(children)
    for parent in problem_parents:
        search_categories.remove(parent)
    search_categories.extend(problem_children)
    search_categories.extend(problem_parents)  # Now at end of list
    # END DUBIOUS WORKAROUND

    for category in search_categories:
        category_id = category['CategoryID']
        category_level = int(category['CategoryLevel'])
        sub_string = 'sub' * (category_level-1)
        print('Loading for {}category {}...'.format(sub_string,
                                                    category_id))
        options = {'CategoryID': category_id,
                   'DetailLevel': 'ReturnAll',
                   'ViewAllNodes': 'true'}
        # BEGIN DUBIOUS WORKAROUND
        # Only look at the top level for this category
        if category_id in problematic_categories:
            options['LevelLimit'] = 1
        # END DUBIOUS WORKAROUND

        try:
            response = api.execute('GetCategoryFeatures', options)
        except ConnectionError as e:
            handle_ebay_error(e)
        response_dict = response.dict()
        test_for_message(response_dict)

        if six.PY2:
            # Convert all strings to unicode
            response_dict = convert_to_unicode(response_dict)

        if features_data is None:
            # First batch of new categories
            features_data = response_dict   # Initialize with the whole dataset
            # Extract all the FeatureDefinition keys
            feature_definitions.update(
                features_data['FeatureDefinitions'].keys())
            # Special-case the ListingDurations
            lds = response_dict['FeatureDefinitions']['ListingDurations']
            features_data['ListingDurationsVersion'] = lds['_Version']
            if 'ListingDuration' in lds:
                for ld in lds['ListingDuration']:
                    listing_durations[ld['_durationSetID']] = ld['Duration']
            del (features_data['FeatureDefinitions'])
        else:
            # Add new categories to existing dictionary
            if 'Category' not in response_dict:
                # No over-ridden categories returned
                continue
            cat_list = response_dict['Category']
            if not isinstance(cat_list, Sequence):
                cat_list = [cat_list]  # in case there is only one category
            # Add the new categories, FeatureDefinitions, ListingDurations
            features_data['Category'].extend(cat_list)
            feature_definitions.update(
                response_dict['FeatureDefinitions'].keys())
            lds = response_dict['FeatureDefinitions']['ListingDurations']
            if 'ListingDuration' in lds:
                for ld in lds['ListingDuration']:
                    if ld['_durationSetID'] in listing_durations:
                        continue
                    listing_durations[ld['_durationSetID']] = ld['Duration']

    # Store the FeatureDefinitions and ListingDurations in a sensible place
    feature_definitions.remove('ListingDurations')
    features_data['FeatureDefinitions'] = feature_definitions
    features_data['ListingDurations'] = listing_durations

    # Move the ConditionHelpURL out of each category and reorganize
    # the Conditions
    for cat in features_data['Category']:
        if 'ConditionValues' in cat:
            cv = cat['ConditionValues']
            if 'ConditionHelpURL' in cv:
                cat['ConditionHelpURL'] = (
                    cv['ConditionHelpURL'])
                del cv['ConditionHelpURL']
            cat['ConditionValues'] = cv['Condition']

    if 'ConditionValues' in features_data['SiteDefaults']:
        cv = features_data['SiteDefaults']['ConditionValues']
        if 'ConditionHelpURL' in cv:
            features_data['SiteDefaults']['ConditionHelpURL'] = (
                cv['ConditionHelpURL'])
            del cv['ConditionHelpURL']
        features_data['SiteDefaults']['ConditionValues'] = cv['Condition']

    # Extract the new version number
    features_version = features_data['CategoryVersion']

    # Return the new features
    return features_version, features_data


def get_eBay_details(site_id=default_site_id):
    """Perform a GeteBayDetails call and save the output in geteBayDetails.txt
    in the site root directory
    """
    filename = os.path.join(frappe.utils.get_site_path(),
                            'GeteBayDetails.txt')

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(domain='api.sandbox.ebay.com', config_file=PATH_TO_YAML,
                      siteid=site_id, warnings=True, timeout=20)

        response = api.execute('GeteBayDetails', {})

    except ConnectionError as e:
        handle_ebay_error(e)

    response_dict = response.dict()
    test_for_message(response_dict)

    with open(filename, 'wt') as f:
        f.write(repr(response_dict))

    return None


#def verify_add_item(listing_dict, site_id=default_site_id):
    #"""Perform a VerifyAddItem call, and return useful information"""

    #try:
        #api = Trading(domain='api.sandbox.ebay.com', config_file=PATH_TO_YAML,
                      #siteid=site_id, warnings=True, timeout=20)

        #response = api.execute('VerifyAddItem', listing_dict)

    #except ConnectionError as e:
        ## traverse the DOM to look for error codes
        #for node in api.response.dom().findall('ErrorCode'):
            #msgprint("error code: %s" % node.text)

        ## check for invalid data - error code 37
        #if 37 in api.response_codes():
            #if 'Errors' in api.response.dict():
                #errors_dict = api.response.dict()['Errors']
                #errors_list = []
                #for key, value in errors_dict.items():
                    #errors_list.append('{} : {}'.format(key, value))
                #msgprint('\n'.join(errors_list))
                #if 'ErrorParameters' in errors_dict:
                    #parameter = errors_dict['ErrorParameters']['Value']
                    #parameter_stack = parameter.split('.')
                    #parameter_value = listing_dict
                    #for stack_entry in parameter_stack:
                        #parameter_value = parameter_value[stack_entry]
                    #msgprint("'{}': '{}'".format(parameter, parameter_value))

        #else:
            #msgprint("Unknown error: {}".format(api.response_codes()))
            #msgprint('{}'.format(e))
            #msgprint('{}'.format(e.response.dict()))
        #return {'ok': False}

    ## Success?
    #ok = True
    #ret_dict = {'ok': ok}

    #msgprint(response.dict())

    #return ret_dict
