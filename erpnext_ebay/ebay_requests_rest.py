# -*- coding: utf-8 -*-
"""eBay request utilities using the REST APIs."""

import datetime
import json

from ebay_rest.error import Error as eBayRestError

import frappe

from .ebay_constants import HOME_GLOBAL_ID
from .ebay_tokens import get_api


def ebay_logger():
    """Return the frappe Logger instance for the eBay logger."""
    return frappe.logger('erpnext_ebay.ebay')


def handle_ebay_error(e):
    """Throw an appropriate Frappe error message on error."""
    ebay_logger().error(f'handle_ebay_error {e}')
    try:
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
        frappe.throw(messages_str)
    except Exception:
        # We have not handled this correctly; just raise the original error.
        raise e


def check_for_warnings(api_response):
    """Test for warning messages."""

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


def get_orders(num_days):
    """Get orders using the Sell Fulfillment API.

    Retrieves orders in the last num_days.
    """

    # Get number of dates and calculated last_modified_date filter
    last_modified_date = (
        datetime.datetime.utcnow() - datetime.timedelta(days=num_days)
    ).isoformat(timespec='milliseconds')
    orders_filter = f"lastmodifieddate:[{last_modified_date}Z..]"
    # Get API and call get_orders
    api = get_api(sandbox=False, marketplace_id=HOME_GLOBAL_ID)
    try:
        pages = api.sell_fulfillment_get_orders(
            field_groups="TAX_BREAKDOWN", filter=orders_filter)

        # Load all orders immediately
        pages = list(pages)
    except eBayRestError as e:
        handle_ebay_error(e)
    # Check for warnings
    check_for_warnings(pages[0])

    orders = []
    for page in pages:
        orders.extend(page['orders'] or [])

    return orders


def get_transactions(num_days=None, buyer_username=None, payout_id=None,
                     transaction_id=None, transaction_type=None,
                     order_id=None):
    """Get transactions using the Sell Finances API.

    Arguments
        num_days: Only return transactions from the last num_days
        buyer_username: Only return transactions involving this buyer
        payout_id: Return transactions relating to this payout
        transaction_id: Return this transaction only
        order_id: Return transactions relating to this sales order
    """

    if transaction_id and not transaction_type:
        frappe.throw(
            'transaction_type must be supplied if transaction_id is used!')

    transaction_filters = []
    if num_days:
        # Get number of dates and calculated last_modified_date filter
        last_transaction_date = (
            datetime.datetime.utcnow() - datetime.timedelta(days=num_days)
        ).isoformat(timespec='milliseconds')
        transaction_filters.append(
            f"transactionDate:[{last_transaction_date}Z..]")
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
    transaction_filters = ','.join(transaction_filters)

    api = get_api(sandbox=False, marketplace_id=HOME_GLOBAL_ID)
    try:
        pages = api.sell_finances_get_transactions(
            filter=transaction_filters)

        # Load all transactions immediately
        pages = list(pages)
    except eBayRestError as e:
        handle_ebay_error(e)
    # Check for warnings
    check_for_warnings(pages[0])

    transactions = []
    for page in pages:
        transactions.extend(page['transactions'] or [])

    return transactions



