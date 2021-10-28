# -*- coding: utf-8 -*-
"""eBay requests which are read-only, and do not affect live eBay data."""

import os
import sys
import time
import threading
import operator

import datetime
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

import redo
import requests

import frappe
from frappe import _, msgprint

from ebaysdk.response import Response
from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

from erpnext_ebay.ebay_constants import (
    EBAY_SITE_NAMES, HOME_SITE_ID,
    REDO_ATTEMPTS, REDO_SLEEPTIME, REDO_SLEEPSCALE
)
from erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings\
    import use_sandbox

PATH_TO_YAML = os.path.join(
    os.sep, frappe.utils.get_bench_path(), 'sites',
    frappe.get_site_path(), 'ebay.yaml')


def ebay_logger():
    """Return the frappe Logger instance for the eBay logger."""
    return frappe.logger('erpnext_ebay.ebay')


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


def handle_ebay_error(e, input_dict=None):
    """Throw an appropriate Frappe error message on error."""
    ebay_logger().error(f'handle_ebay_error {e}')
    try:
        api_dict = e.response.dict()
        if isinstance(api_dict['Errors'], Sequence):
            errors = api_dict['Errors']
        else:
            errors = [api_dict['Errors']]
        if input_dict:
            messages = [str(input_dict)]
        else:
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
                messages.append(f"""eBay error:\n"{error['LongMessage']}""")
        messages_str = '\n'.join(messages)
        ebay_logger().error(messages_str)
        ebay_logger().error(str(api_dict))
        frappe.throw(messages_str)
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
        ebay_logger().info(message)
    # Now check for errors/warnings.
    if 'Errors' not in api_dict:
        return
    if isinstance(api_dict['Errors'], Sequence):
        errors = api_dict['Errors']
    else:
        errors = [api_dict['Errors']]
    messages = []
    for e in errors:
        messages.append(
            f'{e["SeverityCode"]} code {e["ErrorCode"]}: {e["LongMessage"]}')
    messages_str = '\n'.join(messages)
    msgprint(messages_str)
    ebay_logger().warning(messages_str)


def get_trading_api(site_id=HOME_SITE_ID, warnings=True, timeout=20,
                    force_sandbox_value=None, api_call=None, executor=None,
                    **kwargs):
    """Get a TradingAPI instance which can be reused.
    If executor is passed, a ParallelTrading instance is returned instead.
    """
    ebay_logger().debug(f'get_trading_api{" " + api_call if api_call else ""}')

    if frappe.flags.in_test:
        frappe.throw('No eBay API while in test mode!')

    if force_sandbox_value is None:
        sandbox = use_sandbox(api_call)
    else:
        sandbox = bool(force_sandbox_value)

    domain = 'api.sandbox.ebay.com' if sandbox else 'api.ebay.com'

    trading_kwargs = {
        'domain': domain,
        'config_file': PATH_TO_YAML,
        'siteid': site_id,
        'warnings': warnings,
        'timeout': timeout
    }
    trading_kwargs.update(kwargs)

    if executor:
        return ParallelTrading(**trading_kwargs, executor=executor)
    else:
        return Trading(**trading_kwargs)


def get_orders(order_status='All', include_final_value_fees=True,
               num_days=None):
    """Returns a tuple of a list of, and the number of, recent orders
    from the eBay TradingAPI.

    This list is NOT filtered by a siteid as the API call does not filter
    by siteid.
    """

    if num_days is None:
        num_days = int(frappe.get_value(
            'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))

    try:
        if num_days < 1:
            frappe.msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    orders = []
    page = 1

    api_options = {}
    try:
        # Initialize TradingAPI; default timeout is 20.

        # Always use the US site for GetOrders as it returns fields we need
        # (which the UK site, for example, doesn't) and it doesn't filter by
        # siteID anyway

        api = get_trading_api(site_id=0, warnings=True, timeout=20,
                              api_call='GetOrders')

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

            redo.retry(
                api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
                sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
                args=('GetOrders', api_options)
            )

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
        handle_ebay_error(e, api_options)

    return orders, num_days


def get_my_ebay_selling(listings_type='Summary', api_options=None,
                        api_inner_options=None, site_id=HOME_SITE_ID):
    """Returns a list of listings from the GetMyeBaySelling eBay TradingAPI.
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
                              api_call='GetMyeBaySelling')
        while True:
            # TradingAPI results are often paginated, so loop until
            # all pages have been obtained
            if listings_type in INNER_PAGINATE:
                api_options[listings_type]['Pagination'] = {
                    'EntriesPerPage': 100, 'PageNumber': page}

            redo.retry(
                api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
                sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
                args=('GetMyeBaySelling', api_options)
            )

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
                ebay_logger().info(f'n_pages = {n_pages}')
                if ('ItemArray' in listings_api[listings_type]
                        and listings_api[listings_type]['ItemArray']
                        and 'Item' in listings_api[listings_type]['ItemArray']):
                    n_items = len(
                        listings_api[listings_type]['ItemArray']['Item'])
                else:
                    n_items = 0
                ebay_logger().info(f'n_items per page = {n_items}')
            if n_pages > 1:
                ebay_logger().info(f'page {page} / {n_pages}')

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
        handle_ebay_error(e, api_options)

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


def get_seller_list(item_codes=None, site_id=HOME_SITE_ID,
                    output_selector=None, granularity_level='Coarse',
                    detail_level=None, days_before=0, days_after=119,
                    active_only=True, force_sandbox_value=None,
                    print=ebay_logger().info):
    """Runs GetSellerList to obtain a list of items.
    Note that this call does NOT filter by SiteID, but does return it.
    Items are returned ending between days_before now and days_after now, with
    defaults of 0 days before and 119 days after, respectively.
    If active_only is True (the default), only 'Active' items are returns.
    """

    # eBay has a limit of 300 calls in 15 seconds
    MAX_REQUESTS = {'time': 15, 'n_requests': 300}

    # Must not use DetailLevel and GranularityLevel
    if granularity_level and detail_level:
        raise ValueError('Do not use both GranularityLevel and DetailLevel!')

    # Create eBay acceptable datetime stamps for EndTimeTo and EndTimeFrom
    if (days_before < 0) or (days_after < 0):
        frappe.throw('days_before or days_after less than zero!')
    if (days_before + days_after) >= 120:
        frappe.throw('Can only search a total date range of less than 120 days')
    end_from = (
        datetime.datetime.utcnow() - datetime.timedelta(days=days_before)
    ).isoformat(timespec='milliseconds') + 'Z'
    end_to = (
        datetime.datetime.utcnow() + datetime.timedelta(days=days_after)
    ).isoformat(timespec='milliseconds') + 'Z'

    listings = []

    # Create executor for futures
    executor = ThreadPoolExecutor(max_workers=50)

    # If item codes is passed, trim to 50 characters maximum
    if item_codes:
        if any(len(x) > 50 for x in item_codes):
            frappe.msgprint('Warning - some item codes too long for eBay SKUs')
        item_codes = [x[0:50] for x in item_codes]

    api = None
    api_options = {}
    try:
        # Initialize TradingAPI; default timeout is 20.

        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_sandbox_value=force_sandbox_value,
                              api_call='GetSellerList', executor=executor)

        n_pages = None
        page = 1
        futures = []
        api_options = {
            'EndTimeTo': end_to,
            'EndTimeFrom': end_from,
            'Pagination': {
                'EntriesPerPage': 100,
                'PageNumber': page
            },
        }
        if granularity_level:
            api_options['GranularityLevel'] = granularity_level
        if detail_level:
            api_options['DetailLevel'] = detail_level
        if output_selector:
            api_options['OutputSelector'] = [
                'ItemID', 'ItemArray.Item.Site',
                'ItemArray.Item.SellingStatus.ListingStatus',
                'PaginationResult', 'ReturnedItemCountActual',
                ] + output_selector
            for field in output_selector:
                if 'WatchCount' in field:
                    api_options['IncludeWatchCount'] = True
                    break
        if item_codes is not None:
            api_options['SKUArray'] = {'SKU': item_codes}

        # First call to get number of pages
        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GetSellerList', api_options)
        )

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

            api_options['Pagination']['PageNumber'] = page
            redo.retry(
                api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
                sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
                args=('GetSellerList', api_options)
            )

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
        handle_ebay_error(e, api_options)

    finally:
        executor.shutdown()
        if api:
            api.session.close()

    # Filter to get only active listings.
    if active_only:
        listings = [x for x in listings
                    if x['SellingStatus']['ListingStatus'] == 'Active']

    return listings


def get_item(item_id=None, item_code=None, site_id=HOME_SITE_ID,
             output_selector=None):
    """Returns a single listing from the eBay TradingAPI.
    """

    if not (item_code or item_id):
        raise ValueError('No item_code or item_id passed to get_item!')

    api_options = {'IncludeWatchCount': True}
    if output_selector:
        api_options['OutputSelector'] = (
            ['ItemID', 'Item.Site'] + output_selector)
    if item_code:
        api_options['SKU'] = item_code
    if item_id:
        api_options['ItemID'] = item_id
    try:
        # Initialize TradingAPI; default timeout is 20.

        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              api_call='GetItem')

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GetItem', api_options)
        )

        listing = api.response.dict()
        test_for_message(listing)

    except ConnectionError as e:
        handle_ebay_error(e, api_options)

    return listing['Item']


def get_categories_versions(site_id=HOME_SITE_ID):
    """Load the version number of the current eBay categories
    and category features.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              api_call='GetCategories')

        api_options = {'LevelLimit': 1, 'ViewAllNodes': False}
        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GetCategories', api_options)
        )
        response1 = api.response
        test_for_message(response1.dict())

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GetCategoryFeatures', {})
        )
        response2 = api.response
        test_for_message(response2.dict())

    except ConnectionError as e:
        handle_ebay_error(e)

    categories_version = response1.reply.CategoryVersion
    features_version = response2.reply.CategoryVersion

    return (categories_version, features_version)


def get_categories(site_id=HOME_SITE_ID):
    """Load the eBay categories for the categories cache.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=60,
                              api_call='GetCategories')

        api_options = {'DetailLevel': 'ReturnAll', 'ViewAllNodes': 'true'}

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GetCategories', api_options)
        )

    except ConnectionError as e:
        handle_ebay_error(e)

    categories_data = api.response.dict()

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


def get_features(site_id=HOME_SITE_ID):
    """Load the eBay category features for the features cache.
    Always uses the live eBay API.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=60,
                              api_call='GetCategoryFeatures')

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
        print(f'Loading for {substring}category {category_id}...')
        api_options = {
            'CategoryID': category_id,
            'DetailLevel': 'ReturnAll',
            'ViewAllNodes': 'true'
        }
        # BEGIN DUBIOUS WORKAROUND
        # Only look at the top level for this category
        if category_id in problematic_categories:
            api_options['LevelLimit'] = 1
        # END DUBIOUS WORKAROUND

        try:
            redo.retry(
                api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
                sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
                args=('GetCategoryFeatures', api_options)
            )
        except ConnectionError as e:
            handle_ebay_error(e)
        response_dict = api.response.dict()
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


def get_ebay_details(site_id=HOME_SITE_ID, detail_name=None):
    """Perform a GeteBayDetails call.
    """

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              api_call='GeteBayDetails')

        api_options = {}
        if detail_name is not None:
            api_options['DetailName'] = detail_name

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=(ConnectionError,),
            args=('GeteBayDetails', api_options)
        )

    except ConnectionError as e:
        handle_ebay_error(e)

    response_dict = api.response.dict()
    test_for_message(response_dict)

    return response_dict


def get_ebay_details_to_file(site_id=HOME_SITE_ID):
    """Perform a GeteBayDetails call and save the output in geteBayDetails.txt
    in the site root directory.
    """
    filename = os.path.join(frappe.utils.get_site_path(),
                            'GeteBayDetails.txt')

    response_dict = get_ebay_details(site_id)

    with open(filename, 'wt') as f:
        f.write(repr(response_dict))

    return None


def get_cached_ebay_details(details_key, site_id=HOME_SITE_ID,
                            force_update=False):
    """Return the selected eBay Details for the selected site_id.
    Cache for efficiency.
    """
    ALLOWED_DETAILS_KEYS = (
        'CountryDetails', 'CurrencyDetails', 'DispatchTimeMaxDetails',
        'PaymentOptionDetails', 'RegionDetails', 'ShippingLocationDetails',
        'ShippingServiceDetails', 'SiteDetails', 'URLDetails',
        'TimeZoneDetails', 'ItemSpecificDetails', 'RegionOfOriginDetails',
        'ShippingCarrierDetails', 'ReturnPolicyDetails',
        'ListingStartPriceDetails', 'BuyerRequirementDetails',
        'ListingFeatureDetails', 'VariationDetails',
        'ExcludeShippingLocationDetails', 'UpdateTime',
        'RecoupmentPolicyDetails', 'ShippingCategoryDetails', 'ProductDetails'
    )
    if details_key not in ALLOWED_DETAILS_KEYS:
        frappe.throw(f'Details key {key} not permitted!')

    cache_key = f'eBay{details_key}_{site_id}'
    if force_update:
        # Don't load from cache
        details = None
    else:
        details = frappe.cache().get_value(cache_key)

    if details is not None:
        cache_date = datetime.datetime.fromisoformat(details['Timestamp'][:-1])
        cache_age = (datetime.datetime.utcnow() - cache_date).days
        if cache_age == 0:
            # Our cache is still acceptable
            return details[details_key]
    # Either there is no cache, or it is out of date
    # Get a new entry
    details = get_ebay_details(
        site_id=site_id, detail_name=details_key)

    # Store the new values in the cache and return
    frappe.cache().set_value(cache_key, details)

    return details[details_key]


def get_shipping_service_descriptions(site_id=HOME_SITE_ID):
    """Cache the eBay Shipping Details descriptions as a dictionary."""
    # Check the timestamp of the current ShippingServiceDetailsTrans cache
    cache_key = f'eBayShippingServiceDetailsTrans_{site_id}'
    ssd = frappe.cache().get_value(cache_key)
    if ssd:
        cache_age = (datetime.datetime.utcnow() - ssd['datetime']).days
        if cache_age == 0:
            # The cache is still valid
            return ssd['trans_table']

    # We must regenerate the translation table
    shipping_service_details = get_cached_ebay_details(
        'ShippingServiceDetails', site_id
    )

    # Calculate shipping name translation table
    shipping_option_dict = {}
    for shipping_option in shipping_service_details:
        shipping_option_dict[shipping_option['ShippingService']] = (
            shipping_option['Description'])

    ssd = {
        'datetime': datetime.datetime.utcnow(),
        'trans_table': shipping_option_dict
    }

    # Store the new values in the cache and return
    frappe.cache().set_value(cache_key, ssd)

    return shipping_option_dict
