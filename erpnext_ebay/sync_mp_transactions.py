# -*- coding: utf-8 -*-

import collections
import datetime
import operator
import textwrap

import frappe
from erpnext import get_default_currency

from ebay_rest.error import Error as eBayRestError

from .ebay_requests import get_item as get_item_trading, ConnectionError
from .ebay_requests_rest import get_transactions, get_order, get_payouts
from .sync_orders_rest import divide_rounded, ErpnextEbaySyncError, VAT_RATES

MAX_DAYS = 90
COMPANY_ACRONYM = frappe.get_all('Company', fields=['abbr'])[0].abbr

FEE_ITEM = 'ITEM-15487'
EBAY_SUPPLIER = 'eBay'
DOMESTIC_VAT = VAT_RATES[f'Sales - {COMPANY_ACRONYM}']


@frappe.whitelist()
def sync_mp_transactions(num_days=None):
    """Synchronise eBay Managed Payments transactions.
    Create Purchase Invoices that add all fees and charges to
    the eBay Managed Payment account.
    NOTE - this should, ideally, be run just after updating eBay listings
    to help identify items from item IDs.
    """

    default_currency = get_default_currency()
    ebay_bank = f'eBay Managed {default_currency} - {COMPANY_ACRONYM}'
    expense_account = f'eBay Managed Fees - {COMPANY_ACRONYM}'

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay transactions...')

    # Load orders from Ebay
    if num_days is None:
        num_days = int(frappe.get_value(
            'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))

    # Load transactions from eBay
    transactions = get_transactions(num_days=min(num_days, MAX_DAYS))
    transactions.sort(key=operator.itemgetter('transaction_date'))

    # Group transactions by date
    transactions_by_date = collections.defaultdict(list)
    for transaction in transactions:
        transaction_id = transaction['transaction_id']
        # Check for existing PINV entry for this transaction
        if frappe.get_all('Purchase Invoice Item',
                          filters={'ebay_transaction_id': transaction_id}):
            continue
        # Check transaction is not failed
        if transaction['transaction_status'] == 'FAILED':
            continue
        # Get date of transaction
        transaction_datetime = datetime.datetime.strptime(
            transaction['transaction_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        transaction['transaction_datetime'] = transaction_datetime
        transaction_date = transaction_datetime.date()
        transactions_by_date[transaction_date].append(transaction)

    # Create a PINV for each date with transactions
    for posting_date, transactions in transactions_by_date.items():
        pinv_doc = frappe.new_doc('Purchase Invoice').update({
            'title': f'eBay transactions {posting_date}',
            'supplier': EBAY_SUPPLIER,
            'is_paid': True,
            'posting_date': posting_date,
            'set_posting_time': True,
            'update_stock': False,
            'cash_bank_account': ebay_bank,
            'mode_of_payment': f'eBay Managed {default_currency}'
        })
        for transaction in transactions:
            try:
                add_pinv_items(transaction, pinv_doc, default_currency,
                               expense_account)
            except ErpnextEbaySyncError as e:
                # Handle this a bit better
                print(transaction)
                frappe.throw(f'Transaction sync error! {e}', exc=e)
        if not getattr(pinv_doc, 'items', None):
            # If there are no PINV items added, go to next date
            del pinv_doc
            continue
        # Add domestic VAT on eBay fees
        if DOMESTIC_VAT:
            tax_entry = pinv_doc.append('taxes')
            tax_entry.charge_type = 'On Net Total'
            tax_entry.description = f'VAT ({DOMESTIC_VAT*100}%)'
            tax_entry.account_head = f'VAT - {COMPANY_ACRONYM}'
            tax_entry.included_in_print_rate = True
            tax_entry.rate = DOMESTIC_VAT * 100
        # If total effect is negative, make a debit note
        if sum(x.rate * x.qty for x in pinv_doc.items) < 0:
            for item in pinv_doc.items:
                item.qty = -item.qty
            pinv_doc.is_return = True
        # Save and submit PINV
        pinv_doc.insert()
        #pinv_doc.submit()

    return


@frappe.whitelist()
def sync_mp_payouts(num_days=None, payout_account=None):
    """Synchronise eBay Managed Payments payouts.
    Create Journal Entries for payouts from the eBay Managed Payment account.
    """

    default_currency = get_default_currency()
    ebay_bank = f'eBay Managed {default_currency} - {COMPANY_ACRONYM}'

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay transactions...')

    # Load orders from Ebay
    if num_days is None:
        num_days = int(frappe.get_value(
            'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))
    if payout_account is None:
        payout_account = frappe.get_value(
            'eBay Manager Settings', 'eBay Manager Settings',
            'ebay_payout_account')
    if not payout_account:
        raise ErpnextEbaySyncError('No eBay payout account set!')
    currency = (
        frappe.get_value('Account', payout_account, 'account_currency')
        or default_currency
    )

    # Load payouts from eBay
    payouts = get_payouts(num_days=min(num_days, MAX_DAYS))
    payouts.sort(key=operator.itemgetter('payout_date'))

    for payout in payouts:
        if payout['payout_status'] in ('INITIATED', 'RETRYABLE_FAILED',
                                       'TERMINAL_FAILED'):
            # This transaction hasn't happened or didn't happen
            continue
        elif payout['payout_status'] == 'REVERSED':
            raise NotImplementedError('Need to check how this works?')
        if payout['amount']['currency'] != currency:
            raise ErpnextEbaySyncError(
                'Payout account has different currency to eBay payouts')

        # Get date of payout
        payout_datetime = datetime.datetime.strptime(
            payout['payout_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        payout_date = payout_datetime.date()

        pi_amount = float(payout['amount']['value'])
        pi = payout['payout_instrument']
        amount_str = frappe.utils.fmt_money(pi_amount, currency=currency)
        last_four = f"last four digits {pi['account_last_four_digits']}"
        details = textwrap.dedent(
            f"""\
            eBay Payout {payout['payout_id']}
            Payout date: {payout_datetime}
            Payout ID: {payout['payout_id']}
            Paid to {pi['instrument_type']} '{pi['nickname']}' ({last_four})
            {payout['payout_status']}: {payout['payout_status_description']}
            Value: {amount_str}"""
        )

        # Create Journal Entry
        je_doc = frappe.get_doc({
            'doctype': 'Journal Entry',
            'title': f'eBay Managed Payments payout {payout_date}',
            'posting_date': payout_date,
            'user_remark': details,
            'accounts': [
                {
                    'account': ebay_bank,
                    'credit': pi_amount,
                    'credit_in_account_currency': pi_amount
                },
                {
                    'account': payout_account,
                    'debit': pi_amount,
                    'debit_in_account_currency': pi_amount
                }
            ]
        })
        je_doc.insert()
        #je_doc.submit()

    return


def add_pinv_items(transaction, pinv_doc, default_currency, expense_account):
    """Add a PINV item or PINV items as required to the PINV doc supplied,
    based on the supplier transaction.

    Note - transaction['transaction_datetime'] must have been added
    with a datetime object representation of transaction['transaction_date'].
    """

    t = transaction  # Shorthand
    t_id = t['transaction_id']
    t_type = t['transaction_type']
    currency = (
        t['amount']['converted_from_currency'] or t['amount']['currency']
    )
    exchange_rate = float(t['amount']['exchange_rate'] or 0) or 1.0

    # Deal with different transaction types
    if t_type == 'SALE':
        # Transaction for sale order
        if not (t['total_fee_amount'] or t['order_line_items']):
            # Entry with no fees; skip
            return
        # Only add fees (sale amount added by SINV)
        buyer = t['buyer']['username']
        order_id = t['order_id']
        # Sum marketplace fees according to total amount
        li_fee_dict = {}
        li_fee_currency_dict = {}
        for li in t['order_line_items']:
            li_fee = 0
            for mf in li['marketplace_fees']:
                # Check currency
                if mf['amount']['currency'] != currency:
                    raise ErpnextEbaySyncError(
                        f'Transaction {t_id} has inconsistent currencies!')
                if mf['amount']['converted_from_currency']:
                    raise ErpnextEbaySyncError(
                        f'Transaction {t_id} has converted marketplace fees?')
                # Sum fees
                fee = float(mf['amount']['value'])  # in local currency
                li_fee += fee
            li_fee_currency_dict[li['line_item_id']] = li_fee
        if t['amount']['converted_from_currency']:
            # Conversion to home currency
            li_fee_dict = divide_rounded(li_fee_currency_dict,
                                         float(t['amount']['value']))
        else:
            li_fee_dict = li_fee_currency_dict

        # Now loop over each line item and add one PINV for each
        total_fee = 0
        total_fee_currency = 0
        for li in t['order_line_items']:
            item_code = get_item_code_for_order(
                order_id, order_line_item_id=li['line_item_id'])
            pinv_item = pinv_doc.append('items')
            pinv_item.item_code = FEE_ITEM
            pinv_item.ebay_transaction_id = t['transaction_id']
            pinv_item.ebay_order_id = order_id
            pinv_item.ebay_transaction_datetime = t['transaction_datetime']
            pinv_item.ebay_order_line_item_id = li['line_item_id']
            pinv_item.ebay_sku = item_code
            pinv_item.ebay_transaction_currency = currency
            pinv_item.ebay_transaction_exchange_rate = exchange_rate
            pinv_item.ebay_buyer = buyer
            pinv_item.expense_account = expense_account
            details = [
                f"""<div>eBay Order Line Item {li['line_item_id']}</div>""",
                f"""<div>Item code {item_code}</div><ul>"""
            ]
            for mf in li['marketplace_fees']:
                # Sum fees
                fee = float(mf['amount']['value'])  # in local currency
                # Format fee in local (and home) currency
                fee_str = frappe.utils.fmt_money(fee, currency=currency)
                if mf['amount']['currency'] != default_currency:
                    fee_home = frappe.utils.fmt_money(
                        exchange_rate * fee, currency=default_currency)
                    fee_home_str = f""" <i>({fee_home})</i>"""
                else:
                    fee_home_str = ''
                # Format descriptions for this item
                fee_memo = f" ({mf['fee_memo']})" if mf['fee_memo'] else ""
                details.append(f"""<li>{mf['fee_type']}{fee_memo}: """)
                details.append(f"""{fee_str}{fee_home_str}</li>""")
            # Add PINV item for this order line item
            li_id = li['line_item_id']
            li_fee = li_fee_dict[li_id]
            li_fee_currency = li_fee_currency_dict[li_id]
            li_fee_str = frappe.utils.fmt_money(
                li_fee, currency=default_currency)
            if t['amount']['converted_from_currency']:
                li_fee_currency_fmt = frappe.utils.fmt_money(
                    li_fee_currency, currency=currency)
                li_fee_currency_str = f""" ({li_fee_currency_fmt})"""
            else:
                li_fee_currency_str = ''
            details.append(f"""</ul><div>Total: {li_fee_str}"""
                           + f"""{li_fee_currency_str} (inc VAT)</div>""")
            pinv_item.qty = 1
            pinv_item.rate = li_fee
            pinv_item.description = '\n'.join(details)
            total_fee += li_fee_currency
        # Check total fee
        total_fee = round(total_fee, 2)
        if (float(t['total_fee_amount']['value']) != total_fee
                or t['total_fee_amount']['currency'] != currency):
            raise ErpnextEbaySyncError(f'Transaction {t_id} inconsistent fees!')
    elif t_type in ('NON_SALE_CHARGE', 'SHIPPING_LABEL'):
        # Transaction for a non-sale charge (e.g. additional fees)
        # One PINV item
        if t['order_line_items']:
            raise ErpnextEbaySyncError(
                f'{t_type} {t_id} has order line items!')
        item_id = None
        order_id = None
        item_ids = [r['reference_id'] for r in (t['references'] or [])
                    if r['reference_type'] == 'ITEM_ID']
        order_ids = [r['reference_id'] for r in (t['references'] or [])
                     if r['reference_type'] == 'ORDER_ID']
        # Set item_id only if we have a single item ID
        if len(item_ids) == 1:
            item_id = item_ids[0]
        # More than one order ID is an error
        if len(order_ids) == 1:
            order_id = order_ids[0]
        elif len(order_ids) > 1:
            raise ErpnextEbaySyncError(
                f'Transaction {t_id} multiple order references!')
        # Get item code
        if item_id and order_id:
            item_code = get_item_code_for_order(
                order_id, item_id=item_id)
        elif item_id:
            item_code = get_item_code_for_item_id(item_id)
        elif (order_id
                and t['fee_type'] in ('AD_FEE', 'FINAL_VALUE_SHIPPING_FEE')):
            # Some fees come, unhelpfully, with every item ID
            item_code = None
        elif t_type == 'SHIPPING_LABEL':
            # Accept eBay's failure to identify anything
            item_code = None
        else:
            raise ErpnextEbaySyncError(
                f'Cannot identify item for transaction {t_id}')
        # Fee
        # Check currency
        if t['amount']['currency'] != default_currency:
            raise ErpnextEbaySyncError(
                f'Transaction {t_id} not in default currency!')
        # Fee in local quantity
        if t['amount']['converted_from_currency']:
            fee_currency = frappe.utils.fmt_money(
                float(t['amount']['converted_from_value']),
                currency=t['amount']['converted_from_currency']
            )
            fee_currency_str = f""" <i>({fee_currency})</i>'"""
        else:
            fee_currency_str = ''
        # Fee in home currency
        fee = float(t['amount']['value'])
        fee_str = frappe.utils.fmt_money(
            float(t['amount']['value']),
            currency=t['amount']['currency']
        )
        t_memo = t['transaction_memo']
        fee_memo = f" ({t_memo})" if t_memo else ""
        if t_type == 'NON_SALE_CHARGE':
            details = (
                f"""<div>eBay <i>{t_type}</i> Transaction {t_id}</div>
                <div>Item code {item_code or 'not available'}</div>
                <div><i>{t['fee_type']}</i>{fee_memo}
                {fee_str}{fee_currency_str} (inc VAT)</div>"""
            )
        else:
            details = (
                f"""<div>eBay <i>{t_type}</i> Transaction {t_id}</div>
                <div>Shipping label: {fee_memo}
                {fee_str}{fee_currency_str} (inc VAT)</div>"""
            )
        pinv_item = pinv_doc.append('items')
        pinv_item.item_code = FEE_ITEM
        pinv_item.ebay_transaction_id = t['transaction_id']
        pinv_item.ebay_order_id = order_id
        pinv_item.ebay_transaction_datetime = t['transaction_datetime']
        pinv_item.ebay_sku = item_code
        pinv_item.ebay_transaction_currency = currency
        pinv_item.ebay_transaction_exchange_rate = exchange_rate
        pinv_item.expense_account = expense_account
        pinv_item.qty = 1
        pinv_item.rate = fee
        pinv_item.description = details
    elif t_type == 'REFUND':
        # We do only consider the fees here; we assume the SINV will
        # be refunded
        # We don't record against any particular item as we can't do that
        if not t['order_line_items']:
            raise ErpnextEbaySyncError(
                f'REFUND {t_id} has no order line items!')
        order_id = t['order_id']
        order_line_item_ids = [x['line_item_id'] for x in t['order_line_items']]
        item_codes = [
            get_item_code_for_order(order_id, order_line_item_id=x)
            for x in order_line_item_ids
        ]
        # Check currency
        if t['total_fee_amount']['currency'] != default_currency:
            raise ErpnextEbaySyncError(
                f'Transaction {t_id} not in default currency!')
        # Fee in local quantity
        if t['total_fee_amount']['converted_from_currency']:
            fee_currency = frappe.utils.fmt_money(
                float(t['total_fee_amount']['converted_from_value']),
                currency=t['total_fee_amount']['converted_from_currency']
            )
            fee_currency_str = f""" <i>({fee_currency})</i>'"""
        else:
            fee_currency_str = ''
        # Fee in home currency
        fee = float(t['total_fee_amount']['value'])
        fee_str = frappe.utils.fmt_money(
            float(t['total_fee_amount']['value']),
            currency=t['total_fee_amount']['currency']
        )
        t_memo = t['transaction_memo']
        fee_memo = f" ({t_memo})" if t_memo else ""
        details = (
            f"""<div>eBay <i>REFUND (FEES)</i> Transaction {t_id}</div>
            <div>Item codes: {', '.join(item_codes)}</div>
            <div><i>{t['fee_type'] or ''}</i>{fee_memo}
            {fee_str}{fee_currency_str} (inc VAT)</div>"""
        )
        pinv_item = pinv_doc.append('items')
        pinv_item.item_code = FEE_ITEM
        pinv_item.ebay_transaction_id = t['transaction_id']
        pinv_item.ebay_order_id = t['order_id']
        pinv_item.ebay_transaction_datetime = t['transaction_datetime']
        pinv_item.ebay_sku = None  # don't record against any particular item
        pinv_item.ebay_transaction_currency = currency
        pinv_item.ebay_transaction_exchange_rate = exchange_rate
        pinv_item.expense_account = expense_account
        pinv_item.qty = 1
        pinv_item.rate = -fee  # NOTE NEGATIVE because fee is refund
        pinv_item.description = details
    #elif t_type == 'ADJUSTMENT':
        #pass
    #elif t_type == 'CREDIT':
        #pass
    #elif t_type == 'TRANSFER':
        #pass
    else:
        print(t)
        raise ErpnextEbaySyncError(
            f'Transaction {t_id} has unhandled type {t_type}!')

    return None  # The PINV item has been added; no need to return anything


def get_item_code_for_item_id(item_id):
    """Get the item code that matches the (legacy?) item ID supplied.
    First search the zeBayListings table, then call Buy Browse get_item."""
    records = frappe.db.sql("""
        SELECT ebay.sku
        FROM `zeBayListings` as ebay
        WHERE ebay.ebay_id = %(item_id)s;
    """, {'item_id': item_id}, as_dict=True)
    if len(records) > 1:
        raise ErpnextEbaySyncError(f'Too many hits for item {item_id}!')
    elif records:
        return records[0].sku
    # We have not located the item.
    item_data = None
    try:
        item_data = get_item_trading(item_id, output_selector=['SKU'])
    except ConnectionError as e:
        if e.response.dict()['Errors']['ErrorCode'] == 17:
            # Could not find/not allowed error
            raise ErpnextEbaySyncError(f'Could not find {item_id}!')
        else:
            raise
    return item_data['SKU']


def get_item_code_for_order(order_id, order_line_item_id=None, item_id=None):
    """Given an eBay order ID and EITHER an order line item ID OR a (legacy?)
    item ID, get the item code.
    Search through existing Sales Invoices first, and if that fails call
    get_order for the item SKU.
    Note that we do not care if the Sales Invoice is submitted or cancelled.
    """

    params = {
        'order_id': order_id,
        'order_line_item_id': order_line_item_id,
        'item_id': item_id
    }

    if order_line_item_id and item_id:
        raise ValueError('Supply either order_line_item_id or item_id!')

    if order_line_item_id:
        filter_line = """sii.ebay_order_line_item_id = %(order_line_item_id)s"""
    else:
        filter_line = """sii.ebay_item_id = %(item_id)s"""

    # Try loading from SINVs first
    records = frappe.db.sql(f"""
        SELECT sii.item_code
        FROM `tabSales Invoice Item` AS sii
        LEFT JOIN `tabSales Invoice` AS si
            ON sii.parent = si.name
        WHERE si.ebay_order_id = %(order_id)s
            AND {filter_line};
        """, params, as_dict=True)
    item_code = {x.item_code for x in records}
    if len(item_code) > 1:
        raise ValueError(
            f'Multiple results for order {order_id} line '
            + f'item {order_line_item_id or item_id}!'
        )
    if item_code:
        # We have a single result; return it
        item_code, = item_code
        return item_code
    # We will have to look up the order
    try:
        order = get_order(order_id)
    except eBayRestError as e:
        raise ErpnextEbaySyncError(
            f'Unable to load order to get item code!\n{e}')
    for li in order['line_items']:
        if order_line_item_id:
            # Check order line ID
            if li['line_item_id'] == order_line_item_id:
                return li['sku']
        else:
            # Check legacy item ID
            if li['legacy_item_id'] == item_id:
                return li['sku']
    # We could not locate correct line item
    if order_line_item_id:
        msg = f'line item {order_line_item_id}'
    else:
        msg = f'item ID {item_id}'
    raise ErpnextEbaySyncError(f'Order {order_id} did not contain {msg}?')
