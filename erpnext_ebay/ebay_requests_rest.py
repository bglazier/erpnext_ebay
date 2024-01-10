# -*- coding: utf-8 -*-
"""eBay request utilities using the REST APIs."""

import datetime
import json

import redo

import frappe

from erpnext_ebay.ebay_constants import (
    HOME_GLOBAL_ID, REDO_ATTEMPTS, REDO_SLEEPTIME,
    REDO_SLEEPSCALE, REDO_EXCEPTIONS, eBayRestError
)
from erpnext_ebay.ebay_get_requests import ebay_logger
from erpnext_ebay.ebay_tokens import get_api
from erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings\
    import use_sandbox


def handle_ebay_error(e):
    """Throw an appropriate Frappe error message on error."""
    ebay_logger().error(f'handle_ebay_error {e}')
    try:
        if e.detail is None:
            # We don't have anything to work with here; raise the original error
            raise e
        response = json.loads(e.detail)
        errors = response.get('errors', [])
        messages = []
        for error in errors:
            error_id = error['errorId']
            message = error.get('longMessage') or error['message']
            if error_id == 932:
                # eBay auth token has expired
                messages.append(
                    f"""eBay API token has expired:\n{message}"""
                )
            if error_id in (2001, 18000):
                # Too many requests (short-duration threshold)
                messages.append(
                    f"""Too many requests:\n{message}"""
                )
            else:
                # Some other eBay error
                messages.append(
                    f"""eBay {e.reason} error {error_id}:\n{message}"""
                )
        messages_str = '\n'.join(messages)
        ebay_logger().error(messages_str)
        ebay_logger().error(str(errors))
        frappe.throw(messages_str, exc=e)
    except Exception:
        # We have not handled this correctly; just raise the original error.
        raise e


def check_for_warnings(api_response):
    """Test for warning messages."""

    if not (hasattr(api_response, 'get') and callable(api_response.get)):
        # Return value is probably a single value rather than a dictionary
        return
    warnings = api_response.get('warnings', [])
    if not warnings:
        return
    messages = []
    for warning in warnings:
        error_id = warning['errorId']
        message = warning.get('longMessage') or warning['message']
        messages.append(
            f"""eBay warning {error_id}:\n{message}"""
        )
    messages_str = '\n'.join(messages)
    frappe.msgprint(messages_str)
    ebay_logger().warning(messages_str)


def single_api_call(api_call, sandbox=False, *args, **kwargs):
    """Make a non-paged API call. Handles warnings and errors."""
    api = get_api(sandbox=sandbox, marketplace_id=HOME_GLOBAL_ID)
    call = getattr(api, api_call)
    try:
        result = redo.retry(
            call, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=args, kwargs=kwargs
        )
    except eBayRestError as e:
        handle_ebay_error(e)
    # Check for warnings
    check_for_warnings(result)

    return result


def paged_api_call(api_call, record_field, sandbox=False, *args, **kwargs):
    """Make a paged API call. Handles warnings and errors."""
    api = get_api(sandbox=sandbox, marketplace_id=HOME_GLOBAL_ID)
    call = getattr(api, api_call)

    def get_pages(*args, **kwargs):
        return list(call(*args, **kwargs))

    try:
        # Make calls and load all pages immediately
        pages = redo.retry(
            get_pages, attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
            sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS,
            args=args, kwargs=kwargs
        )
    except eBayRestError as e:
        handle_ebay_error(e)

    # Split into records and warnings
    records = [x['record'] for x in pages if 'record' in x]
    page_warnings = [x for x in pages if 'warnings' in x]

    # Check for warnings
    for warnings in page_warnings:
        check_for_warnings(warnings)

    return records


def get_order(order_id, sandbox=False):
    """Get a single order using the Sell Fulfillment API."""
    return single_api_call('sell_fulfillment_get_order', order_id=order_id,
                           field_groups='TAX_BREAKDOWN', sandbox=sandbox)


def get_orders(num_days=None, order_ids=None, sandbox=False, **kwargs):
    """Get orders using the Sell Fulfillment API.

    If num_days is supplied, only orders modified in the last num_days
    are returned.
    If order_ids is supplied, only orders in the list supplied
    are returned.
    """
    kwargs = {}

    # Get number of dates and calculated lastmodifieddate filter
    if num_days:
        last_modified_date = (
            datetime.datetime.utcnow() - datetime.timedelta(days=num_days)
        ).isoformat(timespec='milliseconds')
        kwargs['filter'] = f"lastmodifieddate:[{last_modified_date}Z..]"

    # Add order_ids as comma-separated string
    if order_ids:
        kwargs['order_ids'] = ','.join(order_ids)

    # Make API call
    return paged_api_call('sell_fulfillment_get_orders', 'orders',
                          field_groups='TAX_BREAKDOWN', sandbox=sandbox,
                          **kwargs)


def get_payment_dispute(payment_dispute_id, sandbox=False):
    """Retrieve a single payment dispute."""
    return single_api_call('sell_fulfillment_get_payment_dispute',
                           payment_dispute_id=payment_dispute_id,
                           sandbox=sandbox)


def get_transactions(num_days=None, buyer_username=None, payout_id=None,
                     transaction_id=None, transaction_type=None,
                     order_id=None, start_date=None, end_date=None,
                     sandbox=False, **kwargs):
    """Get transactions using the Sell Finances API.

    Arguments
        num_days: Only return transactions from the last num_days
        buyer_username: Only return transactions involving this buyer
        payout_id: Return transactions relating to this payout
        transaction_id: Return this transaction only
        order_id: Return transactions relating to this sales order
        start_date, end_date: Only transactions between these UTC dates (inc.)
    """

    if transaction_id and not transaction_type:
        frappe.throw(
            'transaction_type must be supplied if transaction_id is used!')

    if bool(start_date) != bool(end_date):
        frappe.throw('Must provide both start_date and end_date or neither!')
    elif num_days and start_date:
        frappe.throw('Use either num_days OR start_date/end_date (or neither)!')

    kwargs = {}
    transaction_filters = []
    if num_days:
        # Get number of dates and calculated last_modified_date filter
        last_transaction_date = (
            datetime.datetime.utcnow() - datetime.timedelta(days=num_days)
        ).isoformat(timespec='milliseconds')
        transaction_filters.append(
            f"transactionDate:[{last_transaction_date}Z..]")
    if start_date:
        # Get transactionDate filter from start and end date filters
        start_dt = (
            datetime.datetime.combine(start_date, datetime.time.min)
            .isoformat(timespec='milliseconds')
        )
        end_dt = (
            datetime.datetime.combine(end_date, datetime.time.max)
            .isoformat(timespec='milliseconds')
        )
        transaction_filters.append(
            f"transactionDate:[{start_dt}Z..{end_dt}Z]")
    if buyer_username:
        transaction_filters.append(f"buyerUsername:{{{buyer_username}}}")
    if transaction_type:
        transaction_filters.append(f"transactionType:{{{transaction_type}}}")
    if transaction_id:
        transaction_filters.append(f"transactionId:{{{transaction_id}}}")
    if payout_id:
        transaction_filters.append(f"payoutId:{{{payout_id}}}")
    if order_id:
        transaction_filters.append(f"orderId:{{{order_id}}}")
    if transaction_filters:
        kwargs['filter'] = ','.join(transaction_filters)

    # Make API call
    return paged_api_call(
        'sell_finances_get_transactions', 'transactions',
        sandbox=sandbox, **kwargs)


def get_payouts(num_days=None, payout_status=None,
                start_date=None, end_date=None, sandbox=False, **kwargs):
    """Get payout using the Sell Finances API.

    Arguments
        num_days: Only return payouts from the last num_days
        payout_status: Only return payouts with this payout status
        start_date, end_date: Only payouts between these UTC dates (inclusive)
    """

    if bool(start_date) != bool(end_date):
        frappe.throw('Must provide both start_date and end_date or neither!')
    elif num_days and start_date:
        frappe.throw('Use either num_days OR start_date/end_date (or neither)!')

    kwargs = {}
    payout_filters = []
    if num_days:
        # Get number of dates and calculated payoutDate filter
        payout_date = (
            datetime.datetime.utcnow() - datetime.timedelta(days=num_days)
        ).isoformat(timespec='milliseconds')
        payout_filters.append(
            f"payoutDate:[{payout_date}Z..]")
    if start_date:
        # Get payoutDate filter from start and end date filters
        start_dt = (
            datetime.datetime.combine(start_date, datetime.time.min)
            .isoformat(timespec='milliseconds')
        )
        end_dt = (
            datetime.datetime.combine(end_date, datetime.time.max)
            .isoformat(timespec='milliseconds')
        )
        payout_filters.append(
            f"payoutDate:[{start_dt}Z..{end_dt}Z]")
    if payout_status:
        payout_filters.append(f"payoutStatus={{{payout_status}}}")
    if payout_filters:
        kwargs['filter'] = ','.join(payout_filters)

    # Make API call
    return paged_api_call(
        'sell_finances_get_payouts', 'payouts', sandbox=sandbox, **kwargs)


def get_transfer(transfer_id, sandbox=False):
    """Retrieve detailed information about a single TRANSFER."""
    return single_api_call('sell_finances_get_transfer',
                           transfer_id=transfer_id, sandbox=sandbox)


def get_item(item_id, *args, sandbox=False, **kwargs):
    """Retrieve a single item using the Buy Browse API.

    Arguments
        item_id: Item ID to look up.
    """

    return single_api_call('buy_browse_get_item', item_id=item_id,
                           sandbox=sandbox, *args, **kwargs)


def get_items(item_ids, sandbox=False, **kwargs):
    """Retrieve up to 20 items at once using the Buy Browse API.

    Arguments
        item_ids: List of Item IDs to look up
    """

    kwargs = {'item_ids': ','.join(item_ids)}

    # Make API call
    return paged_api_call(
        'buy_browse_get_items', 'items', sandbox=sandbox, **kwargs)


def get_shipping_fulfillments(order_id):
    """Get all shipping fulfillments for an eBay order.

    Arguments:
        order_id: eBay order ID

    Returns:
        A list of fulfillment dictionaries with the format:
            - fulfillmentID: Unique ID for the fulfillment
            - shipmentTrackingNumber: Tracking number
            - shippingCarrierCode: Shipping Carrier code (where available)
            - shippedDate: eBay datetime string for date of shipping
            - lineItems: list of dicts for each line item in the shipping
              > lineItemId: eBay line item ID
              > quantity: Quantity in this shipment (not currently returned)
    """

    API_CALL = 'sell_fulfillment_get_shipping_fulfillments'

    return single_api_call(
        API_CALL, use_sandbox(API_CALL),
        order_id=order_id
    ).get('fulfillments', [])


def create_shipping_fulfillment(order_id, shipping_fulfillment):
    """Submit a shipping fulfillment to eBay.

    Arguments:
        order_id: eBay order ID that the shipping fulfillment is for
        shipping_fulfillment: A dictionary containing the shipping fulfillment.

    The shipping fulfillment should include:
        - shippedDate: eBay format datetime for shipping
        - shippingCarrierCode (opt): eBay carrier code for the carrier
        - trackingNumber: Tracking number for the shipment
        - lineItems: list of dicts for each line item in the shipment.
          > lineItemId: eBay line item ID
          > quantity: Quantity shipped in this shipment

    Either both or none of the shippingCarrierCode and trackingNumber
    must be supplied.
    """

    API_CALL = 'sell_fulfillment_create_shipping_fulfillment'

    return single_api_call(
        API_CALL, use_sandbox(API_CALL),
        body=shipping_fulfillment, order_id=order_id
    )
