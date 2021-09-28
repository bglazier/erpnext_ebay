# -*- coding: utf-8 -*-
"""eBay requests related to revising item data. These are not read-only, and
will affect live eBay data.
"""

from ebaysdk.exception import ConnectionError

from erpnext_ebay.ebay_constants import HOME_SITE_ID
from erpnext_ebay.ebay_get_requests import (
    ebay_logger, get_trading_api, handle_ebay_error, test_for_message)
from erpnext_ebay.ebay_do_requests import trading_api_call


def revise_inventory_status(items, site_id=HOME_SITE_ID):
    """Perform a ReviseInventoryStatus call."""

    api_dict = {'InventoryStatus': items}
    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, api_call='ReviseInventoryStatus',
                              warnings=True, timeout=20)
        ebay_logger().info(f'Relisting inventory: {items}')

        response = api.execute('ReviseInventoryStatus', api_dict)

    except ConnectionError as e:
        handle_ebay_error(e, api_dict)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def relist_item(ebay_id, site_id=HOME_SITE_ID, item_dict=None):
    """Perform a RelistItem call."""

    relist_dict = {'Item': item_dict or {}}
    relist_dict['Item']['ItemID'] = ebay_id

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, api_call='RelistItem',
                              warnings=True, timeout=20)
        ebay_logger().info(f'Relisting item: {relist_dict}')

        response = api.execute('RelistItem', relist_dict)

    except ConnectionError as e:
        handle_ebay_error(e, relist_dict)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def revise_item(ebay_id, site_id=HOME_SITE_ID, item_dict=None):
    """Perform a ReviseItem call."""

    revise_dict = {'Item': item_dict or {}}
    revise_dict['Item']['ItemID'] = ebay_id

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, api_call='ReviseItem',
                              warnings=True, timeout=20)
        ebay_logger().info(f'Revising item: {revise_dict}')

        response = api.execute('ReviseItem', revise_dict)

    except ConnectionError as e:
        handle_ebay_error(e, revise_dict)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def end_items(items, site_id=HOME_SITE_ID):
    """Perform an EndItems call."""

    # MessageID is (contrary to documentation) apparently required for
    # this call (per request container), so add it
    for item in items:
        item['MessageID'] = item['ItemID']
    api_dict = {'EndItemRequestContainer': items}

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20)
        ebay_logger().info(f'Ending items {[x["ItemID"] for x in items]}')

        response = api.execute('EndItems', api_dict)

    except ConnectionError as e:
        handle_ebay_error(e, api_dict)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict
