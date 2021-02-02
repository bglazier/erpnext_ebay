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


def verify_add_item(listing_dict, site_id=default_site_id):
    """Perform a VerifyAddItem call, and return useful information"""

    try:
        api = get_trading_api(site_id=site_id, warnings=True, timeout=20,
                              force_sandbox=True)

        response = api.execute('VerifyAddItem', listing_dict)

    except ConnectionError as e:
        handle_ebay_error(e)
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

    return response.dict()
