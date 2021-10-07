# -*- coding: utf-8 -*-
"""eBay requests which are not read-only, and can affect live eBay data.
Excludes item revision calls.
"""

from ebaysdk.exception import ConnectionError

from erpnext_ebay.ebay_constants import HOME_SITE_ID
from erpnext_ebay.ebay_get_requests import (
    ebay_logger, get_trading_api, handle_ebay_error, test_for_message)
from erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings\
    import use_sandbox


def trading_api_call(api_call, input_dict, site_id=HOME_SITE_ID,
                     force_sandbox_value=None, escape_xml=True):
    """Perform a TradingAPI call with an input dictionary."""

    try:
        api = get_trading_api(site_id=site_id, api_call=api_call,
                              warnings=True, timeout=20,
                              force_sandbox_value=force_sandbox_value,
                              escape_xml=escape_xml)

        response = api.execute(api_call, input_dict)

    except ConnectionError as e:
        handle_ebay_error(e, input_dict)

    return response.dict()


def ebay_message_to_partner(user_id, item_id, body, subject,
                            message_details=None):
    """Send a message to a buyer or seller using
    the AddMemberMessageAAQToPartner call.

    Note that HTML cannot be used in the body of this message.
    """

    if message_details is None:
        message_details = {}

    message_dict = {
        'ItemID': item_id,
        'MemberMessage': {
            'Body': body,
            'QuestionType': 'Shipping',
            'RecipientID': user_id,
            'Subject': subject
        },
    }

    message_dict['MemberMessage'].update(message_details)

    return trading_api_call('AddMemberMessageAAQToPartner', message_dict)


def add_item(item_code, item_details=None):
    """Add an item for testing purposes."""

    # Check we are using the Sandbox
    if not use_sandbox('AddItem'):
        raise ValueError('Must use sandbox!')

    if item_details is None:
        item_details = {}

    item_dict = {
        'Country': 'GB',
        'Currency': 'GBP',
        'Description': '<![CDATA[<p>This is a test item.</p>]]>',
        'DispatchTimeMax': 3,
        'ListingDuration': 'GTC',
        'ListingType': 'FixedPriceItem',
        'Location': 'A galaxy far, far away',
        'PaymentMethods': ['CashOnPickup', 'PayPal'],
        'PayPalEmailAddress': 'test@example.com',
        'PictureDetails': {
            'PictureURL': ['https://picsum.photos/id/1020/500']
        },
        'PrimaryCategory': {
            'CategoryID': '29223'
        },
        'Quantity': 1,
        'ReturnPolicy': {
            'ReturnsAcceptedOption': 'ReturnsAccepted'
        },
        'ShipToLocations': ['None'],
        'Site': 'UK',
        'SKU': item_code,
        'StartPrice': 10.0,
        'Title': 'TestItem: Test Item erpnext_ebay'
    }

    item_dict.update(item_details)

    return trading_api_call('AddItem', {'Item': item_dict},
                            force_sandbox_value=True)
