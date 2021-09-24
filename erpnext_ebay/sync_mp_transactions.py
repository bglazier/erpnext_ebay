# -*- coding: utf-8 -*-

import collections
import datetime
import json
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

FEE_ITEM = 'ITEM-15847'
EBAY_SUPPLIER = 'eBay'
DOMESTIC_VAT = VAT_RATES[f'Sales - {COMPANY_ACRONYM}']


def date_range(start_date, end_date):
    """Yield all dates between start_date and end_date, *inclusive*.
    Based on https://stackoverflow.com/a/32616832/1427742
    """
    for ordinal in range(start_date.toordinal(), end_date.toordinal() + 1):
        yield datetime.date.fromordinal(ordinal)


@frappe.whitelist()
def archive_transactions(start_date, end_date):
    """Archive all transactions and payouts between start_date and
    end_date (inclusive). Raises an error is end_date is on or later
    than today's UTC date.
    Stores all entries in a database table as JSON-encoded entries.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    # Convert string or datetime arguments to date objects (e.g. from JS)
    if not (start_date and end_date):
        frappe.throw('Must have start and end dates!')
    start_date = frappe.utils.getdate(start_date)
    end_date = frappe.utils.getdate(end_date)

    # Check start and end date (inclusive) are reasonable
    if end_date < start_date:
        frappe.throw('Start date after end date!')
    if end_date >= datetime.datetime.now().date():
        frappe.throw('Cannot archive dates on or after current UTC date!')
    dates = tuple(date_range(start_date, end_date))

    # Create table if it does not exist
    frappe.db.sql("""
        CREATE TABLE IF NOT EXISTS `zeBayTransactions`
        (
            posting_date DATE PRIMARY KEY,
            transactions MEDIUMTEXT NOT NULL,
            payouts MEDIUMTEXT NOT NULL
        );
        """)
    # Get transactions
    transactions_by_date = {x: [] for x in dates}
    transactions = get_transactions(start_date=start_date, end_date=end_date)
    transactions.sort(key=operator.itemgetter('transaction_date'))
    for transaction in transactions:
        # Get date of transaction and append to list
        transaction_date = datetime.datetime.strptime(
            transaction['transaction_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        ).date()
        # Find item code(s) of transaction, if any
        transaction['item_codes'] = find_item_codes(transaction)
        transactions_by_date[transaction_date].append(transaction)

    # Get payouts
    payouts_by_date = {x: [] for x in dates}
    payouts = get_payouts(start_date=start_date, end_date=end_date)
    payouts.sort(key=operator.itemgetter('payout_date'))
    for payout in payouts:
        # Get date of payout and append to list
        payout_date = datetime.datetime.strptime(
            payout['payout_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        ).date()
        payouts_by_date[payout_date].append(payout)

    # Save transactions and payouts in table
    for entry_date in dates:
        t_data = transactions_by_date[entry_date]
        p_data = payouts_by_date[entry_date]
        if not (t_data or p_data):
            # No transactions or payouts for this date
            frappe.db.sql("""
                DELETE FROM `zeBayTransactions`
                    WHERE posting_date = %(posting_date)s;
            """, {'posting_date': entry_date})
        else:
            # Store transactions and payouts
            params = {
                'posting_date': entry_date,
                'transactions': json.dumps(t_data),
                'payouts': json.dumps(p_data)
            }
            frappe.db.sql("""
                REPLACE INTO `zeBayTransactions`
                VALUES (%(posting_date)s, %(transactions)s, %(payouts)s);
            """, params)

    frappe.db.commit()


@frappe.whitelist()
def sync_mp_transactions(num_days=None, not_today=False,
                         start_date=None, end_date=None,
                         payout_account=None):
    """Synchronise eBay Managed Payments transactions.
    Create Purchase Invoices that add all fees and charges to
    the eBay Managed Payment account.

    Will also create Journal Entries for TRANSFER transactions.

    Arguments:
        num_days: Include transactions from the last num_days days.
        not_today: If set, transactions from today are not included.
        start_date, end_date: Include transactions in this range.
    Only one of num_days or start_date and end_date should be used.
    NOTE - this should, ideally, be run just after updating eBay listings
    to help identify items from item IDs.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay transactions...')

    default_currency = get_default_currency()
    ebay_bank = f'eBay Managed {default_currency} - {COMPANY_ACRONYM}'
    expense_account = f'eBay Managed Fees - {COMPANY_ACRONYM}'
    today = datetime.date.today()
    if payout_account is None:
        payout_account = frappe.get_value(
            'eBay Manager Settings', 'eBay Manager Settings',
            'ebay_payout_account')
    if not payout_account:
        raise ErpnextEbaySyncError('No eBay payout account set!')
    payout_currency = (
        frappe.get_value('Account', payout_account, 'account_currency')
        or default_currency
    )

    if num_days and (start_date or end_date):
        frappe.throw('Must have num_days OR start_date/end_date, not both!')

    if start_date or end_date:
        # If using start_date and end_date, check we have both and then
        # convert if necessary.
        if not (start_date and end_date):
            frappe.throw('Must have both start and end dates, or neither!')
        start_date = frappe.utils.getdate(start_date)
        end_date = frappe.utils.getdate(end_date)
    elif num_days is None:
        # If not using start_date/end_date and num_days not supplied,
        # get from eBay Manager Settings.
        num_days = int(frappe.get_value(
            'eBay Manager Settings', filters=None, fieldname='ebay_sync_days'))

    # Load transactions from eBay
    if num_days:
        num_days = min(num_days, MAX_DAYS)
    transactions = get_transactions(num_days=num_days,
                                    start_date=start_date, end_date=end_date)
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
        # Check transaction is not held (will be deleted and re-added later
        if transaction['transaction_status'] == 'FUNDS_ON_HOLD':
            continue
        # Get date of transaction
        transaction_datetime = datetime.datetime.strptime(
            transaction['transaction_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        transaction['transaction_datetime'] = transaction_datetime
        transaction_date = transaction_datetime.date()
        if not_today and (transaction_date == today):
            # Don't include transactions from today if not_today set
            continue
        transactions_by_date[transaction_date].append(transaction)

    # Accumulate any transfer transactions that should be dealt with
    # separately
    transfer_transactions = []

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
                               expense_account, transfer_transactions)
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
        # We need to set quantities negative (for debit note to validate)
        # which means we also need to set rates * -1
        pinv_doc.paid_amount = sum(x.rate * x.qty for x in pinv_doc.items)
        if pinv_doc.paid_amount < 0:
            for item in pinv_doc.items:
                item.qty = -item.qty
                item.rate = -item.rate
            pinv_doc.is_return = True
        # Save and submit PINV
        pinv_doc.insert()
        if not pinv_doc.flags.do_not_submit:
            pinv_doc.submit()

    # Now create Journal Entries for TRANSFER transactions
    for t in transfer_transactions:
        t_id = t['transaction_id']

        # Check status of transfer transaction
        t_status = t['transaction_status']
        if t_status == 'PAYOUT':
            # This transaction is not completed yet
            continue
        elif t_status == 'COMPLETED':
            # This transaction is completed and can be added
            pass
        elif t_status == 'FAILED':
            # This transaction failed, and does not need to be added
            continue
        else:
            raise ErpnextEbaySyncError(
                f'Transfer {t_id} has unhandled status {t_status}')
        t_date = t['transaction_datetime'].date()

        # Check for existing journal entry for this transaction
        if frappe.get_all(
                'Journal Entry',
                filters={
                    'cheque_no': t_id,
                    'cheque_date': t_date,
                    'title': ['like', 'eBay Managed Payments transfer%']
                }):
            continue
        if t['amount']['currency'] != payout_currency:
            raise ErpnextEbaySyncError(
                'Payout account has different currency to transfer')

        t_amount = float(t['amount']['value'])
        amount_str = frappe.utils.fmt_money(
            t_amount, currency=payout_currency)
        credit = t['booking_entry'] == 'CREDIT'
        details = textwrap.dedent(
            f"""\
            eBay Transfer transaction {t_id}
            Transfer date: {t['transaction_datetime']}
            {t['transaction_memo']}
            Transfer from {'seller to eBay' if credit else 'eBay to seller'}
            Payout ID: {t['payout_id']}
            Value: {amount_str}"""
        )

        if credit:
            from_acct = payout_account
            to_acct = ebay_bank
        else:
            from_acct = ebay_bank
            to_acct = payout_account

        # Create Journal Entry
        je_doc = frappe.get_doc({
            'doctype': 'Journal Entry',
            'title': f'eBay Managed Payments transfer {t_date}',
            'posting_date': t_date,
            'user_remark': details,
            'cheque_no': t_id,
            'cheque_date': t_date,
            'accounts': [
                {
                    'account': to_acct,
                    'debit': t_amount,
                    'debit_in_account_currency': t_amount
                },
                {
                    'account': from_acct,
                    'credit': t_amount,
                    'credit_in_account_currency': t_amount
                }
            ]
        })
        je_doc.insert()
        je_doc.submit()

    frappe.msgprint('Finished.')

    return


@frappe.whitelist()
def sync_mp_payouts(num_days=None, payout_account=None):
    """Synchronise eBay Managed Payments payouts.
    Create Journal Entries for payouts from the eBay Managed Payment account.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay payouts...')

    default_currency = get_default_currency()
    ebay_bank = f'eBay Managed {default_currency} - {COMPANY_ACRONYM}'

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
        p_id = payout['payout_id']

        # Get date of payout
        payout_datetime = datetime.datetime.strptime(
            payout['payout_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        payout_date = payout_datetime.date()

        # Check for existing journal entry for this transaction
        if frappe.get_all(
                'Journal Entry',
                filters={
                    'cheque_no': p_id,
                    'cheque_date': payout_date,
                    'title': ['like', 'eBay Managed Payments Payout%']
                }):
            continue

        # Check payout succeeded
        if payout['payout_status'] in ('INITIATED', 'RETRYABLE_FAILED',
                                       'TERMINAL_FAILED'):
            # This transaction hasn't happened or didn't happen
            continue
        elif payout['payout_status'] == 'REVERSED':
            raise NotImplementedError('Need to check how this works?')
        if payout['amount']['currency'] != currency:
            raise ErpnextEbaySyncError(
                'Payout account has different currency to eBay payouts')

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
            'cheque_no': payout['payout_id'],
            'cheque_date': payout_date,
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
        je_doc.submit()

    frappe.msgprint('Finished.')

    return


def add_pinv_items(transaction, pinv_doc, default_currency, expense_account,
                   transfer_transactions):
    """Add a PINV item or PINV items as required to the PINV doc supplied,
    based on the supplier transaction.

    Note - transaction['transaction_datetime'] must have been added
    with a datetime object representation of transaction['transaction_date'].

    Any transactions with a type of 'TRANSFER' are not added to a PINV,
    but are instead appended to transfer_transactions, as these should
    instead create Journal Entries.
    """

    t = transaction  # Shorthand
    t_id = t['transaction_id']
    t_type = t['transaction_type']
    currency = (
        t['amount']['converted_from_currency'] or t['amount']['currency']
    )
    exchange_rate = float(t['amount']['exchange_rate'] or 0) or 1.0
    # Is this a debit or credit entry?
    MULT_DICT = {'CREDIT': -1, 'DEBIT': 1}
    multiplier = MULT_DICT[t['booking_entry']]

    # Deal with different transaction types
    if t_type in ('SALE', 'REFUND'):
        # Transaction for sale order or refund
        if not (t['total_fee_amount'] or t['order_line_items']):
            # Entry with no fees; skip
            return
        # Only add fees (sale/refund amount added by SINV)
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
            if t['total_fee_amount']['currency'] != currency:
                raise ErpnextEbaySyncError(
                    f'Transaction {t_id} has inconsistent currencies!')
            fee_amount = float(t['total_fee_amount']['value']) * exchange_rate
            li_fee_dict = divide_rounded(li_fee_currency_dict, fee_amount)
        else:
            li_fee_dict = li_fee_currency_dict

        # Now loop over each line item and add one PINV item for each
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
                f"""<div>eBay <i>{t_type} (FEES)</i> Transaction {t_id}</div>
                <div>eBay Order Line Item {li['line_item_id']}</div>
                <div>Item code {item_code}</div><ul>"""
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
            # NOTE fee is negative compared to multiplier
            # (so removing money for SALE, adding for REFUND)
            pinv_item.rate = -li_fee * multiplier
            pinv_item.description = '\n'.join(details)
            total_fee += li_fee_currency
        # Check total fee
        total_fee = round(total_fee, 2)
        if (float(t['total_fee_amount']['value']) != total_fee
                or t['total_fee_amount']['currency'] != currency):
            raise ErpnextEbaySyncError(f'Transaction {t_id} inconsistent fees!')
    elif t_type in ('NON_SALE_CHARGE', 'SHIPPING_LABEL', 'DISPUTE', 'CREDIT',
                    'ADJUSTMENT'):
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
        reference_types = {r['reference_type'] for r in (t['references'] or [])}
        if t['order_id'] and (t['order_id'] not in order_ids):
            order_ids.append(t['order_id'])
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
        elif (order_id and t_type in ('DISPUTE', 'CREDIT')):
            # Disputes and dispute credits come with no item ID
            item_code = None
        elif 'INVOICE' in reference_types:
            # Invoices not linked to any individual item (e.g. monthly fee)
            # Don't submit as VAT can be wrong
            item_code = None
            pinv_doc.flags.do_not_submit = True
        elif t['fee_type'] == 'OTHER_FEES':
            # Some fees are not associated with items at all
            item_code = None
        elif t_type == 'SHIPPING_LABEL':
            # Accept eBay's failure to identify anything
            item_code = None
        elif t_type == 'ADJUSTMENT':
            # No item or order ID for adjustments
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
            fee_currency_str = f""" <i>({fee_currency})</i>"""
        else:
            fee_currency_str = ''
        # Fee in home currency
        fee = float(t['amount']['value'])
        fee_str = frappe.utils.fmt_money(
            float(t['amount']['value']),
            currency=t['amount']['currency']
        )
        t_memo = t['transaction_memo']
        t_memo_str = f" ({t_memo})" if t_memo else ""
        if item_code:
            item_code_line = f"""<div>Item code {item_code}</div>"""
        else:
            item_code_line = ""
        if t['fee_type']:
            fee_type_str = f"""<i>{t['fee_type']}</i>"""
        else:
            fee_type_str = ""
        details = (
            f"""<div>eBay <i>{t_type}</i> Transaction {t_id}</div>
            {item_code_line}
            <div>{fee_type_str}{t_memo_str}
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
        pinv_item.rate = fee * multiplier
        pinv_item.description = details
    elif t_type == 'TRANSFER':
        # This transaction cannot be processed as a PINV item, and
        # must instead be passed to sync_mp_payouts.
        transfer_transactions.append(t)
    else:
        print(t)
        raise ErpnextEbaySyncError(
            f'Transaction {t_id} has unhandled type {t_type}!')

    return None  # The PINV item has been added; no need to return anything


def find_item_codes(transaction):
    """From a transaction, return a list of all identified item codes."""
    t = transaction
    item_codes = []
    if t['transaction_type'] in ('SALE', 'REFUND'):
        # Search using line item IDs and order_id
        for oli in (t['order_line_items'] or []):
            li_id = oli['line_item_id']
            item_codes.append(
                get_item_code_for_order(t['order_id'], order_line_item_id=li_id)
            )
    else:
        # Search for ITEM reference
        for ref in (transaction['references'] or []):
            if ref['reference_type'] == 'ITEM_ID':
                item_codes.append(
                    get_item_code_for_item_id(ref['reference_id'])
                )

    return item_codes


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
