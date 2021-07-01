# -*- coding: utf-8 -*-

import collections
import datetime

import frappe
from erpnext import get_default_currency

from ebay_rest.error import Error as eBayRestError

from .ebay_requests_rest import get_transactions, get_order
from .sync_orders_rest import ErpnextEbaySyncError, VAT_RATES

MAX_DAYS = 90
COMPANY_ACRONYM = frappe.get_all('Company', fields=['abbr'])[0].abbr

FEE_ITEM = 'ITEM-15487'
EBAY_SUPPLIER = 'eBay'
DOMESTIC_VAT = VAT_RATES[f'Sales - {COMPANY_ACRONYM}']

@frappe.whitelist()
def sync_mp_transactions():
    """Synchronise eBay Managed Payments transactions.
    Create Purchase Invoices that add all fees and charges to
    the eBay Managed Payment account.
    NOTE - this must be run just after updating eBay listings as
    the Rest APIs provide no way to get the SKU of an eBay listing
    from the line_item_id.
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
    num_days = int(frappe.get_value(
        'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))

    # Load transactions from eBay
    transactions = get_transactions(num_days=min(num_days, MAX_DAYS))

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
        # Save and submit PINV
        pinv_doc.insert()
        #pinv_doc.submit()

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
        # Only add fees (sale amount added by SINV)
        buyer = t['buyer']['username']
        total_fee = 0
        for li in t['order_line_items']:
            # One PINV item per order line item
            item_code = get_item_code_for_order(
                t['order_id'], order_line_item_id=li['line_item_id'])
            pinv_item = pinv_doc.append('items')
            pinv_item.item_code = FEE_ITEM
            pinv_item.ebay_transaction_id = t['transaction_id']
            pinv_item.ebay_order_id = t['order_id']
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
            li_fee = 0
            for mf in li['marketplace_fees']:
                # Check currency
                if mf['amount']['currency'] != default_currency:
                    raise ErpnextEbaySyncError(
                        f'Transaction {t_id} not '
                        + 'in default currency!')
                # Fee in local quantity
                if mf['amount']['converted_from_currency']:
                    fee_currency = frappe.utils.fmt_money(
                        float(mf['amount']['converted_from_value']),
                        currency=mf['amount']['converted_from_currency']
                    )
                    fee_currency_str = f""" <i>({fee_currency})</i>'"""
                else:
                    fee_currency_str = ''
                # Fee in home currency
                fee = float(mf['amount']['value'])
                fee_str = frappe.utils.fmt_money(
                    float(mf['amount']['value']),
                    currency=mf['amount']['currency']
                )
                # Sum fees
                li_fee += fee
                total_fee += fee
                # Format descriptions for this item
                fee_memo = f" ({mf['fee_memo']})" if mf['fee_memo'] else ""
                details.append(f"""<li>{mf['fee_type']}{fee_memo}: """)
                details.append(f"""{fee_str}{fee_currency_str}</li>""")
            # Add PINV item for this order line item
            li_fee = round(li_fee, 2)
            li_fee_str = frappe.utils.fmt_money(
                li_fee, currency=default_currency)
            details.append(f"""</ul><div>Total: {li_fee_str} (inc VAT)</div>""")
            pinv_item.qty = 1
            pinv_item.rate = li_fee
            pinv_item.description = '\n'.join(details)
        # Check total fee
        total_fee = round(total_fee, 2)
        if (float(t['total_fee_amount']['value']) != total_fee
                or t['total_fee_amount']['currency'] != default_currency):
            raise ErpnextEbaySyncError(f'Transaction {t_id} inconsistent fees!')
    #elif t_type == 'ADJUSTMENT':
        #pass
    #elif t_type == 'CREDIT':
        #pass
    elif t_type == 'NON_SALE_CHARGE':
        # Transaction for a non-sale charge (e.g. additional fees)
        # One PINV item
        if t['order_line_items']:
            raise ErpnextEbaySyncError(
                f'NON_SALE_CHARGE {t_id} has order line items!')
        item_id = None
        order_id = None
        for r in t['references']:
            if r['reference_type'] == 'ITEM_ID':
                # We have an item ID reference
                if item_id:
                    raise ErpnextEbaySyncError(
                        f'Transaction {t_id} multiple item references!')
                item_id = r['reference_id']
            elif r['reference_type'] == 'ORDER_ID':
                # We have an order ID reference
                if order_id:
                    raise ErpnextEbaySyncError(
                        f'Transaction {t_id} multiple order references!')
                order_id = r['reference_id']
        # Get item code
        if item_id and order_id:
            item_code = get_item_code_for_order(
                order_id, item_id=item_id)
        elif item_id:
            get_item_code_for_item_id(item_id)
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
        details = (
            f"""<div>eBay <i>NON_SALE_CHARGE</i> Transaction {t_id}</div>
            <div>Item code {item_code}</div>
            <div><i>{t['fee_type']}</i>{fee_memo}
            {fee_str}{fee_currency_str} (inc VAT)</div>"""
        )
        pinv_item = pinv_doc.append('items')
        pinv_item.item_code = FEE_ITEM
        pinv_item.ebay_transaction_id = t['transaction_id']
        pinv_item.ebay_order_id = t['order_id']
        pinv_item.ebay_transaction_datetime = t['transaction_datetime']
        pinv_item.ebay_sku = item_code
        pinv_item.ebay_transaction_currency = currency
        pinv_item.ebay_transaction_exchange_rate = exchange_rate
        pinv_item.expense_account = expense_account
        pinv_item.qty = 1
        pinv_item.rate = fee
        pinv_item.description = details
    #elif t_type == 'REFUND':
        #pass
    #elif t_type == 'SHIPPING_LABEL':
        #pass
    #elif t_type == 'TRANSFER':
        #pass
    else:
        print(t)
        raise ErpnextEbaySyncError(
            f'Transaction {t_id} has unhandled type {t_type}!')

    return None  # The PINV item has been added; no need to return anything


def get_item_code_for_item_id(item_id):
    """Get the item code that matches the (legacy?) item ID supplied."""
    raise NotImplementedError('do this!')


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













