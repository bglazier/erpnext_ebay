# Copyright (c) 2013, Ben Glazier and contributors
# For license information, please see license.txt

import datetime
import json
import operator

import frappe
from erpnext import get_default_currency


def cur_flt(value):
    """Convert to 2dp rounded float if not None, else None."""
    if value is None:
        return None
    return round(float(value), 2)


COLUMNS = [
    {
        'fieldname': 'matched',
        'label': 'Match',
        'fieldtype': 'Check',
        'width': 69
    },
    {
        'fieldname': 'transaction_datetime',
        'label': 'Date and time (UTC)',
        'fieldtype': 'Datetime',
        'width': 150
    },
    {
        'fieldname': 'transaction_id',
        'label': 'ID',
        'fieldtype': 'Data',
        'width': 150
    },
    {
        'fieldname': 'transaction_type',
        'label': 'Type',
        'fieldtype': 'Data',
        'width': 150
    },
    {
        'fieldname': 'booking_entry',
        'label': '',
        'fieldtype': 'Select',
        'options': 'CREDIT\nDEBIT',
        'width': 60
    },
    {
        'fieldname': 'amount',
        'label': 'Amount',
        'fieldtype': 'Currency',
        'width': 80
    },
    {
        'fieldname': 'converted_from',
        'label': 'Amount',
        'fieldtype': 'Currency',
        'options': 'currency',
        'width': 80
    },
    {
        'fieldname': 'currency',
        'label': 'Currency',
        'fieldtype': 'Link',
        'options': 'Currency',
        'width': 60
    },
    {
        'fieldname': 'exchange_rate',
        'label': 'Exc. rate',
        'fieldtype': 'Float',
        'precision': 6,
        'width': 70
    },
    {
        'fieldname': 'link_doctype',
        'label': 'Linked DocType',
        'fieldtype': 'Link',
        'options': 'DocType'
    },
    {
        'fieldname': 'link_docname',
        'label': 'Linked Document',
        'fieldtype': 'Dynamic Link',
        'options': 'link_doctype'
    },
    {
        'fieldname': 'link_booking_entry',
        'label': '',
        'fieldtype': 'Select',
        'options': 'CREDIT\nDEBIT',
        'width': 60
    },
    {
        'fieldname': 'link_amount',
        'label': 'Linked Value',
        'fieldtype': 'Currency'
    },
    {
        'fieldname': 'item_code',
        'label': 'Item Code',
        'fieldtype': 'Link',
        'options': 'Item'
    }
]


def execute(filters=None):
    """Show all transactions and payouts in the archived data."""

    default_currency = get_default_currency()
    company_acronym = frappe.get_all('Company', fields=['abbr'])[0].abbr
    ebay_bank = f'eBay Managed {default_currency} - {company_acronym}'

    data = []
    if not filters:
        return [], []

    start_date = filters.get('start_date')
    end_date = filters.get('end_date')
    if not (start_date and end_date):
        return [], []

    entries = frappe.db.sql("""
        SELECT posting_date, transactions, payouts
        FROM `zeBayTransactions`
            WHERE posting_date >= %(start_date)s
                AND posting_date <= %(end_date)s;
        """, {'start_date': start_date, 'end_date': end_date}, as_dict=True)

    transactions = []
    payouts = []
    for entry in entries:
        transactions.extend(json.loads(entry.transactions))
        payouts.extend(json.loads(entry.payouts))

    # Loop over transactions and add entries
    for t in transactions:
        if t['transaction_status'] == 'FAILED':
            # Skip failed transactions
            continue
        t_datetime = datetime.datetime.strptime(
            t['transaction_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        amount = t['amount']
        fees = t['total_fee_amount']
        currency = amount['converted_from_currency']  # Non-local currency
        er = amount['exchange_rate']
        exchange_rate = None if (er is None) else float(er)
        if amount['currency'] != default_currency:
            frappe.throw('Wrong default currency!')
        if t['transaction_type'] not in ('SALE', 'REFUND'):
            # Simple entry to add
            if t['total_fee_amount'] and t['total_fee_amount']['value']:
                frappe.throw('Non SALE/RETURN has fees!')
            data.append({
                'transaction_datetime': t_datetime,
                'transaction_id': t['transaction_id'],
                'transaction_type': t['transaction_type'],
                'booking_entry': t['booking_entry'],
                'amount': cur_flt(amount['value']),
                'converted_from': cur_flt(amount['converted_from_value']),
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
                'link_booking_entry': None,
                'link_amount': None,
                'item_code': None,
                'transaction': t
            })
        else:
            # Deal with SALE and REFUND differently in two steps
            fee_value = 0.0
            if fees and fees['value']:
                fee_value = cur_flt(fees['value'])
            if currency:
                fee_converted_from_value = fee_value
                fee_value *= exchange_rate
            else:
                fee_converted_from_value = None
            sale_value = float(amount['value']) + fee_value
            if currency:
                sale_converted_from_value = (
                    float(amount['converted_from_value']) + fee_converted_from_value
                )
            else:
                sale_converted_from_value = None
            # Add sale/refund entry
            data.append({
                'transaction_datetime': t_datetime,
                'transaction_id': t['transaction_id'],
                'transaction_type': t['transaction_type'],
                'booking_entry': t['booking_entry'],
                'amount': cur_flt(sale_value),
                'converted_from': cur_flt(sale_converted_from_value),
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
                'link_booking_entry': None,
                'link_amount': None,
                'item_code': None,
                'transaction': t
            })
            # Add fee entry
            if fee_value:
                fee_booking_entry = (
                    'CREDIT' if t['booking_entry'] == 'DEBIT' else 'DEBIT'
                )
                data.append({
                    'transaction_datetime': t_datetime,
                    'transaction_id': t['transaction_id'],
                    'item_code': None,
                    'transaction_type': t['transaction_type'] + ' FEES',
                    'booking_entry': fee_booking_entry,
                    'amount': cur_flt(fee_value),
                    'converted_from': cur_flt(fee_converted_from_value),
                    'currency': currency,
                    'exchange_rate': exchange_rate,
                    'link_doctype': None,
                    'link_docname': None,
                    'link_booking_entry': None,
                    'link_amount': None,
                    'item_code': None,
                    'transaction': t
                })

    # Loop over payouts and add entries
    for p in payouts:
        if p['payout_status'] in ('INITIATED', 'RETRYABLE_FAILED',
                                  'TERMINAL_FAILED'):
            # This payout hasn't happened or didn't happen
            continue
        elif p['payout_status'] == 'REVERSED':
            raise NotImplementedError('Need to check how this works?')
        if p['amount']['currency'] != default_currency:
            frappe.throw('Non-default eBay payout currency')

        p_datetime = datetime.datetime.strptime(
            p['payout_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )

        data.append({
            'transaction_datetime': p_datetime,
            'transaction_id': p['payout_id'],
            'transaction_type': 'PAYOUT',
            'booking_entry': 'DEBIT',
            'amount': cur_flt(p['amount']['value']),
            'converted_from': None,
            'currency': None,
            'exchange_rate': None,
            'link_doctype': None,
            'link_docname': None,
            'link_amount': None,
            'item_code': None,
            'payout': p
        })

    # Add linked documents
    for t in data:
        t_type = t['transaction_type']
        t_id = t['transaction_id']
        if t_type in ('SALE', 'REFUND'):
            # Find a Sales Invoice with this order ID
            order_id = t['transaction']['order_id']
            sinv = frappe.get_all(
                'Sales Invoice',
                fields=['name', 'docstatus'],
                filters={'ebay_order_id': order_id}
            )
            if not sinv:
                # No identified SINV
                continue
            sinv = sinv[0]  # ebay_order_id is a unique field
            while sinv['docstatus'] == 2:
                amended = frappe.get_all(
                    'Sales Invoice',
                    fields=['name', 'docstatus'],
                    filters={'amended_from': sinv.name}
                )
                if not amended:
                    # Could not find amended document from cancelled SINV?
                    sinv = None
                    break
                if len(amended) > 1:
                    frappe.throw('Multiple amended_from?')
                sinv = amended[0]
            if not sinv:
                # Only found cancelled SINVs?
                continue
            if t_type == 'REFUND':
                return_sinv = frappe.get_all(
                    'Sales Invoice',
                    fields=['name'],
                    filters={
                        'return_against': sinv.name,
                        'docstatus': ['!=', 2]
                    }
                )
                if not return_sinv:
                    # Did not find return
                    continue
                sinv = return_sinv[0]
            if sinv.docstatus == 0:
                # Draft SINV: don't include payment value
                payment_value = None
            else:
                # Find GL entry for payment to eBay Managed Payments account
                gl_entries = frappe.get_all(
                    'GL Entry',
                    fields=['credit', 'debit'],
                    filters={
                        'voucher_type': 'Sales Invoice',
                        'voucher_no': sinv.name,
                        'account': ebay_bank
                    }
                )
                if len(gl_entries) != 1:
                    frappe.throw('Wrong GL entries?')
                payment_value = gl_entries[0].debit - gl_entries[0].credit
            # Now add link
            t['link_doctype'] = 'Sales Invoice'
            t['link_docname'] = sinv.name
            if payment_value:
                if t_type == 'SALE':
                    t['link_booking_entry'] = 'CREDIT'
                    t['link_amount'] = cur_flt(payment_value)
                else:
                    t['link_booking_entry'] = 'DEBIT'
                    t['link_amount'] = cur_flt(-payment_value)
        elif t_type == 'PAYOUT':
            # Find a Journal Entry with this payout ID
            je = frappe.get_all(
                'Journal Entry',
                fields=['name'],
                filters={
                    'cheque_no': t['transaction_id'],
                    'docstatus': 1
                }
            )
            if not je:
                # No Journal Entries found
                continue
            elif len(je) > 1:
                # Too many Journal Entries
                frappe.throw('Multiple journal entries!')
            jea = frappe.get_all(
                'Journal Entry Account',
                fields=['credit', 'debit'],
                filters={
                    'account': ebay_bank,
                    'parent': je[0].name
                }
            )
            if not jea:
                frappe.throw('Missing eBay bank account!')
            elif len(jea) > 1:
                frappe.throw('Too many eBay bank account entries!')
            # Note this entry in the JE is for money moving _from_ eBay
            # (another entry will be the money moving _to_ a bank account)
            payout_value = jea[0].credit - jea[0].debit
            if payout_value < 0:
                frappe.throw('Negative payout amount!')
            # Now add link
            t['link_doctype'] = 'Journal Entry'
            t['link_docname'] = je[0].name
            t['link_booking_entry'] = 'DEBIT'
            t['link_amount'] = cur_flt(payout_value)
        else:
            # Find submitted PINV items with this transaction ID
            pinv_items = frappe.get_all(
                'Purchase Invoice Item',
                fields=['name', 'amount', 'parent', 'docstatus'],
                filters={
                    'ebay_transaction_id': t_id,
                    'docstatus': ['!=', 2]
                }
            )
            if not pinv_items:
                # No identified PINVs
                continue
            # Check for multiple parents
            parents = {x.parent for x in pinv_items}
            t['link_doctype'] = 'Purchase Invoice'
            if len(parents) > 1:
                t['link_docname'] = 'Various'
            else:
                t['link_docname'] = pinv_items[0].parent
            submitted_sum = round(sum(
                x.amount for x in pinv_items if x.docstatus == 1
            ), 2)
            if submitted_sum > 0:
                t['link_booking_entry'] = 'DEBIT'
            elif submitted_sum < 0:
                t['link_booking_entry'] = 'CREDIT'
                submitted_sum *= -1
            t['link_amount'] = submitted_sum or None

    # Check if values are matched
    for t in data:
        t['matched'] = (
            t['amount'] == t['link_amount']
            and t['booking_entry'] == t['link_booking_entry']
        )

    data.sort(key=operator.itemgetter('transaction_datetime'))

    # Remove the transaction/payout links
    for t in data:
        t.pop('transaction', None)
        t.pop('payout', None)

    return COLUMNS, data























