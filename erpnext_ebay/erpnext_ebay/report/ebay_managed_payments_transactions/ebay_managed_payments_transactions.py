# Copyright (c) 2013, Ben Glazier and contributors
# For license information, please see license.txt

import datetime
import json
import operator

import frappe
from erpnext import get_default_currency


def flt(value):
    """Convert to float if not None, else None."""
    if value is None:
        return None
    return float(value)


COLUMNS = [
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
        exchange_rate = flt(amount['exchange_rate'])
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
                'amount': flt(amount['value']),
                'converted_from': flt(amount['converted_from_value']),
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
                'link_amount': None,
                'item_code': None,
                'transaction': t
            })
        else:
            # Deal with SALE and REFUND differently in two steps
            fee_value = 0.0
            if fees and fees['value']:
                fee_value = flt(fees['value'])
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
                'amount': sale_value,
                'converted_from': sale_converted_from_value,
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
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
                    'amount': fee_value,
                    'converted_from': fee_converted_from_value,
                    'currency': currency,
                    'exchange_rate': exchange_rate,
                    'link_doctype': None,
                    'link_docname': None,
                    'link_amount': None,
                    'item_code': None,
                    'transaction': t
                })

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
            t['link_amount'] = payment_value
        elif t_type == 'PAYOUT':
            # Find a Journal Entry with this payout ID
            pass
        else:
            # Find PINV items with this transaction ID
            pass

    data.sort(key=operator.itemgetter('transaction_datetime'))

    # Remove the transaction links
    for t in data:
        del t['transaction']

    return COLUMNS, data























