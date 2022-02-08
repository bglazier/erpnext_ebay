# -*- coding: utf-8 -*-
"""eBay requests related to revising item data. These are not read-only, and
will affect live eBay data.
"""

import redo

from ebaysdk.exception import ConnectionError

from erpnext_ebay.ebay_constants import (
    EBAY_TIMEOUT, HOME_SITE_ID, REDO_ATTEMPTS, REDO_SLEEPTIME,
    REDO_SLEEPSCALE, REDO_EXCEPTIONS
)
from erpnext_ebay.ebay_get_requests import (
    ebay_logger, get_trading_api, handle_ebay_error, test_for_message)
from erpnext_ebay.ebay_do_requests import trading_api_call


def revise_inventory_status(items, site_id=HOME_SITE_ID):
    """Perform a ReviseInventoryStatus call."""

    api_options = {'InventoryStatus': items}
    try:
        # Initialize TradingAPI
        api = get_trading_api(site_id=site_id, api_call='ReviseInventoryStatus',
                              warnings=True, timeout=EBAY_TIMEOUT)
        ebay_logger().info(f'Relisting inventory: {items}')

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=('ReviseInventoryStatus', api_options)
        )

    except ConnectionError as e:
        handle_ebay_error(e, api_options)

    response_dict = api.response.dict()
    test_for_message(response_dict)

    return response_dict


def relist_item(ebay_id, site_id=HOME_SITE_ID, item_dict=None):
    """Perform a RelistItem call."""

    relist_dict = {'Item': item_dict or {}}
    relist_dict['Item']['ItemID'] = ebay_id

    try:
        # Initialize TradingAPI
        api = get_trading_api(site_id=site_id, api_call='RelistItem',
                              warnings=True, timeout=EBAY_TIMEOUT)
        ebay_logger().info(f'Relisting item: {relist_dict}')

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=('RelistItem', relist_dict)
        )

    except ConnectionError as e:
        handle_ebay_error(e, relist_dict)

    response_dict = api.response.dict()
    test_for_message(response_dict)

    return response_dict


def revise_item(ebay_id, site_id=HOME_SITE_ID, item_dict=None):
    """Perform a ReviseItem call."""

    revise_dict = {'Item': item_dict or {}}
    revise_dict['Item']['ItemID'] = ebay_id

    try:
        # Initialize TradingAPI
        api = get_trading_api(site_id=site_id, api_call='ReviseItem',
                              warnings=True, timeout=EBAY_TIMEOUT)
        ebay_logger().info(f'Revising item: {revise_dict}')

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=('ReviseItem', revise_dict)
        )

    except ConnectionError as e:
        handle_ebay_error(e, revise_dict)

    response_dict = api.response.dict()
    test_for_message(response_dict)

    return response_dict


def end_items(items, site_id=HOME_SITE_ID):
    """Perform an EndItems call."""

    # MessageID is (contrary to documentation) apparently required for
    # this call (per request container), so add it
    for item in items:
        item['MessageID'] = item['ItemID']
    api_options = {'EndItemRequestContainer': items}

    try:
        # Initialize TradingAPI
        api = get_trading_api(site_id=site_id, warnings=True,
                              timeout=EBAY_TIMEOUT)
        ebay_logger().info(f'Ending items {[x["ItemID"] for x in items]}')

        redo.retry(
            api.execute, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=('EndItems', api_options)
        )

    except ConnectionError as e:
        handle_ebay_error(e, api_options)

    response_dict = api.response.dict()
    test_for_message(response_dict)

    return response_dict
