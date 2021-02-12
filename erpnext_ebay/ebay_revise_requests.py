# -*- coding: utf-8 -*-
"""eBay requests which are not read-only, and cab affect live eBay data."""

from ebaysdk.exception import ConnectionError

from erpnext_ebay.ebay_requests import (
    get_trading_api, handle_ebay_error, test_for_message,
    default_site_id)


def revise_inventory_status(items, site_id=default_site_id):
    """Perform a ReviseInventoryStatus call."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20)

        response = api.execute('ReviseInventoryStatus',
                               {'InventoryStatus': items})

    except ConnectionError as e:
        handle_ebay_error(e)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def end_items(items, site_id=default_site_id):
    """Perform an EndItems call."""

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20)
        # MessageID is (contrary to documentation) apparently required for
        # this call (per request container), so add it
        for item in items:
            item['MessageID'] = item['ItemID']

        response = api.execute('EndItems',
                               {'EndItemRequestContainer': items})

    except ConnectionError as e:
        handle_ebay_error(e)

    response_dict = response.dict()
    test_for_message(response_dict)

    return response_dict


def trading_api_call(api_call, input_dict, site_id=default_site_id,
                     force_sandbox=None):
    """Perform a TradingAPI call with an input dictionary."""

    try:
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_sandbox=force_sandbox)

        response = api.execute(api_call, input_dict)

    except ConnectionError as e:
        handle_ebay_error(e)

    return response.dict()
