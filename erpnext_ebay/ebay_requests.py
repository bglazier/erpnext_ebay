# -*- coding: utf-8 -*-
"""eBay requests which are read-only, and do not affect live eBay data."""

import os
import sys
import time
import threading
import operator

from datetime import datetime, timedelta
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import frappe
from frappe import _, msgprint

from ebaysdk.response import Response
from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

from .ebay_constants import EBAY_SITE_NAMES
from erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings\
    import use_sandbox

PATH_TO_YAML = os.path.join(
    os.sep, frappe.utils.get_bench_path(), 'sites',
    frappe.get_site_path(), 'ebay.yaml')

default_site_id = 3  # eBay site id: 0=US, 3=UK


class ParallelTrading(Trading):
    def __init__(self, executor=None, **kwargs):
        self.executor = executor or ThreadPoolExecutor()
        self.error_check_lock = threading.Lock()
        super().__init__(**kwargs)

    def _execute_request_thread(self, r):
        response = requests.request(
            r.method, r.url, data=r.body, headers=r.headers, verify=True,
            proxies=self.proxies, timeout=self.timeout, allow_redirects=True)

        if hasattr(response, 'content'):
            response = self._process_response(response)

            with self.error_check_lock:
                self.response = response
                if response.status_code != 200:
                    self._response_error = response.reason

                self.error_check()

        return response

    def execute_request(self):
        func = self._execute_request_thread
        self.future = self.executor.submit(func, self.request)

    def _process_response(self, response, parse_response=True):
        """Post processing of the response"""

        return Response(response,
                        verb=self.verb,
                        list_nodes=self._list_nodes,
                        datetime_nodes=self.datetime_nodes,
                        parse_response=parse_response)


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
                messages.append(
                    f"""eBay API token has expired:\n{error['LongMessage']}""")
            if error['ErrorCode'] == "18000":
                # Too many requests (short-duration threshold)
                messages.append(
                    f"""Too many requests:\n{error['LongMessage']}""")
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


def get_trading_api(site_id=default_site_id, warnings=True, timeout=20,
                    force_live_site=False, force_sandbox=False,
                    executor=None):
    """Get a TradingAPI instance which can be reused.
    If executor is passed, a ParallelTrading instance is returned instead.
    """

    if force_live_site and force_sandbox:
        raise ValueError('Cannot force both live and sandbox APIs!')
    elif force_live_site:
        sandbox = False
    elif force_sandbox:
        sandbox = True
    else:
        sandbox = use_sandbox()

    domain = 'api.sandbox.ebay.com' if sandbox else 'api.ebay.com'

    kwargs = {
        'domain': domain,
        'config_file': PATH_TO_YAML,
        'siteid': site_id,
        'warnings': warnings,
        'timeout': timeout
    }

    if executor:
        return ParallelTrading(**kwargs, executor=executor)
    else:
        return Trading(**kwargs)


def get_orders(order_status='All', include_final_value_fees=True):
    """Returns a list of recent orders from the eBay TradingAPI.

    This list is NOT filtered by a siteid as the API call does not filter
    by siteid.
    Always uses the live eBay API.
    """

    num_days = int(frappe.get_value(
        'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))

    try:
        if num_days < 1:
            frappe.msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    orders = []
    page = 1

    try:
        # Initialize TradingAPI; default timeout is 20.

        # Always use the US site for GetOrders as it returns fields we need
        # (which the UK site, for example, doesn't) and it doesn't filter by
        # siteID anyway

        api = get_trading_api(site_id=0, warnings=True, timeout=20,
                              force_live_site=True)

        while True:
            # TradingAPI results are paginated, so loop until
            # all pages have been obtained
            api_options = {
                'NumberOfDays': num_days,
                'OrderStatus': order_status,
                'Pagination': {
                    'EntriesPerPage': 50,
                    'PageNumber': page}
                }
            if include_final_value_fees:
                api_options['IncludeFinalValueFee'] = 'true'

            api.execute('GetOrders', api_options)

            orders_api = api.response.dict()
            test_for_message(orders_api)

            n_orders = int(orders_api['ReturnedOrderCountActual'])
            if n_orders > 0:
                if not isinstance(orders_api['OrderArray']['Order'], list):
                    raise AssertionError('Invalid type in get_orders!')
                orders.extend(orders_api['OrderArray']['Order'])
            if orders_api['HasMoreOrders'] == 'false':
                break
            page += 1

    except ConnectionError as e:
        handle_ebay_error(e)

    return orders, num_days


def get_my_ebay_selling(listings_type='Summary', api_options=None,
                        api_inner_options=None, site_id=default_site_id):
    """Returns a list of listings from the GetMyeBaySelling eBay TradingAPI.
    Always uses the live eBay API.
    """

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

        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_live_site=True)
        while True:
            # TradingAPI results are often paginated, so loop until
            # all pages have been obtained
            if listings_type in INNER_PAGINATE:
                api_options[listings_type]['Pagination'] = {
                    'EntriesPerPage': 100, 'PageNumber': page}

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
                    if 'PaginationResult' in listings_api[listings_type]:
                        n_pages = int(
                            (listings_api[listings_type]
                                ['PaginationResult']['TotalNumberOfPages']))
                    else:
                        n_pages = 1
                print('n_pages = ', n_pages)
                if ('ItemArray' in listings_api[listings_type]
                        and listings_api[listings_type]['ItemArray']
                        and 'Item' in listings_api[listings_type]['ItemArray']):
                    n_items = len(
                        listings_api[listings_type]['ItemArray']['Item'])
                else:
                    n_items = 0
                print(f'n_items per page = {n_items}')
            if n_pages > 1:
                print('page {} / {}'.format(page, n_pages))

            # Locate the appropriate results
            field, array = RESPONSE_FIELDS[listings_type]
            if field is None:
                listings = listings_api
            elif array is None:
                listings = (
                    listings_api[field] if field in listings_api else None)
            else:
                entries = listings_api[listings_type][field][array]
                # Check for single (non-list) entry
                if isinstance(entries, Sequence):
                    listings.extend(entries)
                else:
                    listings.append(entries)

            # If we are on the last page or there are no pages, break.
            if page >= (n_pages or 0):
                break
            page += 1

    except ConnectionError as e:
        handle_ebay_error(e)

    return listings, summary


def get_active_listings():
    """Returns a list of active listings from GetMyeBaySelling."""

    outer_opts = {'OutputSelector': ['ItemID', 'SKU',
                                     'ListingType', 'PaginationResult']}
    inner_opts = {'Include': 'true',
                  'IncludeWatchCount': 'true'}

    listings, _summary = get_my_ebay_selling(
        'ActiveList', outer_opts, inner_opts)

    return listings


def get_seller_list(item_codes=None, site_id=default_site_id,
                    output_selector=None, granularity_level='Coarse',
                    print=print):
    """Runs GetSellerList to obtain a list of (active) items.
    Note that this call does NOT filter by SiteID, but does return it.
    Always uses the live eBay API.
    """

    # eBay has a limit of 300 calls in 15 seconds
    MAX_REQUESTS = {'time': 15, 'n_requests': 300}

    # Create eBay acceptable datetime stamps for EndTimeTo and EndTimeFrom
    end_from = datetime.utcnow().isoformat()[:-3] + 'Z'
    end_to = (datetime.utcnow() + timedelta(days=119)).isoformat()[:-3] + 'Z'

    listings = []

    # Create executor for futures
    executor = ThreadPoolExecutor(max_workers=50)

    try:
        # Initialize TradingAPI; default timeout is 20.

        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_live_site=True, executor=executor)

        n_pages = None
        page = 1
        futures = []
        api_dict = {
            'EndTimeTo': end_to,
            'EndTimeFrom': end_from,
            'GranularityLevel': granularity_level,
            'Pagination': {
                'EntriesPerPage': 100,
                'PageNumber': page},
            }
        if output_selector:
            api_dict['OutputSelector'] = [
                'ItemID', 'ItemArray.Item.Site',
                'ItemArray.Item.SellingStatus.ListingStatus',
                'PaginationResult', 'ReturnedItemCountActual',
                ] + output_selector
            for field in output_selector:
                if 'WatchCount' in field:
                    api_dict['IncludeWatchCount'] = True
                    break
        if item_codes is not None:
            api_dict['SKUArray'] = {'SKU': item_codes}

        # First call to get number of pages
        api.execute('GetSellerList', api_dict)
        response = api.future.result()

        listings_api = response.dict()

        n_listings = int(listings_api['ReturnedItemCountActual'])
        if n_listings == 1:
            listings.append(listings_api['ItemArray']['Item'])
        elif int(listings_api['ReturnedItemCountActual']) > 0:
            listings.extend(listings_api['ItemArray']['Item'])

        n_pages = int(
            listings_api['PaginationResult']['TotalNumberOfPages'])
        total_entries = listings_api[
            'PaginationResult']['TotalNumberOfEntries']
        print(f'n_pages = {n_pages}')
        print(f'total number of items: {total_entries}')
        print(f'n_items per page = {n_listings}')

        # Generate list of futures, rate-limiting in blocks of time
        start_time = time.monotonic()
        n_requests = 0
        print('Creating requests')
        for page in range(2, n_pages+1):
            # Rate limiting
            if n_requests > MAX_REQUESTS['n_requests']:
                dt = time.monotonic() - start_time
                if dt < MAX_REQUESTS['time']:
                    time.sleep(MAX_REQUESTS['time'] - dt)
                n_requests = 0
                start_time = time.monotonic()

            api_dict['Pagination']['PageNumber'] = page
            api.execute('GetSellerList', api_dict)
            api.future.page_number = page
            futures.append(api.future)
            n_requests += 1

        # Loop over the completed futures and process responses
        print('Processing responses')
        for future in as_completed(futures):
            response = future.result()
            listings_api = response.dict()
            test_for_message(listings_api)

            n_listings = int(listings_api['ReturnedItemCountActual'])
            if n_listings == 1:
                listings.append(listings_api['ItemArray']['Item'])
            elif int(listings_api['ReturnedItemCountActual']) > 0:
                listings.extend(listings_api['ItemArray']['Item'])

            print(f'page {future.page_number} / {n_pages} ({n_listings} items)')

            # Ping the database so we don't time out on interactive console
            frappe.db.sql("""SELECT 1""")
            frappe.db.commit()

    except ConnectionError as e:
        handle_ebay_error(e)

    finally:
        executor.shutdown()
        api.session.close()

    listings = [x for x in listings
                if x['SellingStatus']['ListingStatus'] == 'Active']

    return listings


def get_item(item_id=None, item_code=None, site_id=default_site_id,
             output_selector=None, force_sandbox=False):
    """Returns a single listing from the eBay TradingAPI.
    Always uses the live eBay API unless forced otherwise.
    """

    if not (item_code or item_id):
        raise ValueError('No item_code or item_id passed to get_item!')

    api_dict = {'IncludeWatchCount': True}
    if output_selector:
        api_dict['OutputSelector'] = ['ItemID', 'Item.Site'] + output_selector
    if item_code:
        api_dict['SKU'] = item_code
    if item_id:
        api_dict['ItemID'] = item_id
    try:
        # Initialize TradingAPI; default timeout is 20.

        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_live_site=not force_sandbox)

        api.execute('GetItem', api_dict)

        listing = api.response.dict()
        test_for_message(listing)

    except ConnectionError as e:
        handle_ebay_error(e)

    return listing['Item']


def get_categories_versions(site_id=default_site_id):
    """Load the version number of the current eBay categories
    and category features.
    Always uses the live eBay API.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_live_site=True)

        response1 = api.execute('GetCategories', {'LevelLimit': 1,
                                                  'ViewAllNodes': False})
        test_for_message(response1.dict())

        response2 = api.execute('GetCategoryFeatures', {})
        test_for_message(response2.dict())

    except ConnectionError as e:
        handle_ebay_error(e)

    categories_version = response1.reply.CategoryVersion
    features_version = response2.reply.CategoryVersion

    return (categories_version, features_version)


def get_categories(site_id=default_site_id):
    """Load the eBay categories for the categories cache.
    Always uses the live eBay API.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=60,
                              force_live_site=True)

        response = api.execute('GetCategories', {'DetailLevel': 'ReturnAll',
                                                 'ViewAllNodes': 'true'})

    except ConnectionError as e:
        handle_ebay_error(e)

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
        for cat in list(level_dict.values()):
            parent = levels[parent_level][cat['CategoryParentID']]
            parent['Children'].append(cat)

    # Sort the Children list of each category according to its CategoryName
    for cat in cl:
        cat['Children'].sort(key=operator.itemgetter('CategoryName'))

    # Sort the top level list according to the CategoryName of the categories
    top_level = list(levels[1].values())
    top_level.sort(key=operator.itemgetter('CategoryName'))

    categories_data['TopLevel'] = top_level

    del categories_data['CategoryArray']

    # Return the new categories
    return categories_data, max_level


def get_features(site_id=default_site_id):
    """Load the eBay category features for the features cache.
    Always uses the live eBay API.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=60,
                              force_live_site=True)

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


def get_eBay_details(site_id=default_site_id, detail_name=None):
    """Perform a GeteBayDetails call.
    Always uses the live eBay API.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_live_site=True)

        api_options = {}
        if detail_name is not None:
            api_options['DetailName'] = detail_name

        response = api.execute('GeteBayDetails', api_options)

    except ConnectionError as e:
        handle_ebay_error(e)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def get_eBay_details_to_file(site_id=default_site_id):
    """Perform a GeteBayDetails call and save the output in geteBayDetails.txt
    in the site root directory.
    """
    filename = os.path.join(frappe.utils.get_site_path(),
                            'GeteBayDetails.txt')

    response_dict = get_eBay_details(site_id)

    with open(filename, 'wt') as f:
        f.write(repr(response_dict))

    return None


def get_shipping_details(site_id=default_site_id):
    """Cache the eBay Shipping Details entries."""
    cache_key = 'eBayShippingDetails_{}'.format(site_id)
    shipping_details = frappe.cache().get_value(cache_key)
    if shipping_details is not None:
        timestamp = shipping_details['Timestamp'][0:-5]
        cache_date = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
        age = (datetime.utcnow() - cache_date).days
        if age == 0:
            # Our cache is still acceptable
            return shipping_details
    # Either there is no cache, or it is out of date
    # Get a new entry
    shipping_details = get_eBay_details(
        site_id=site_id, detail_name='ShippingServiceDetails')

    # Calculate shipping name translation table
    shipping_option_dict = {}
    for shipping_option in shipping_details['ShippingServiceDetails']:
        shipping_option_dict[shipping_option['ShippingService']] = (
            shipping_option['Description'])

    shipping_details['ShippingOptionDescriptions'] = shipping_option_dict

    # Store the new values in the cache and return
    frappe.cache().set_value(cache_key, shipping_details)

    return shipping_details
