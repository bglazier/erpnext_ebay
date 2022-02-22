# Copyright (c) 2013, Ben Glazier and contributors
# For license information, please see license.txt

import datetime
import json
import operator
from collections import defaultdict

import frappe
from erpnext import get_default_currency


def cur_flt(value, multiplier=1.0):
    """Convert to 2dp rounded float if not None, else None."""
    if value is None:
        return None
    return round(float(value) * multiplier, 2)


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
        'fieldname': 'order_id',
        'label': 'eBay order ID',
        'fieldtype': 'Data',
        'width': 120
    },
    {
        'fieldname': 'item_codes',
        'label': 'Item Code(s)',
        'fieldtype': 'HTML',
        'width': 250
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

    only_mismatches = filters.get('mismatches', False)
    start_date = filters.get('start_date')
    end_date = filters.get('end_date')
    if not (start_date and end_date):
        return [], []
    start_date = frappe.utils.getdate(start_date)
    end_date = frappe.utils.getdate(end_date)

    # Get all transactions and payouts in time period
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

    # Set of all linked documents
    linked_documents = set()

    # Loop over transactions and add entries
    for t in transactions:
        if t['transaction_status'] in ('FAILED', 'FUNDS_ON_HOLD'):
            # Skip failed and on-hold transactions
            continue
        t_datetime = datetime.datetime.strptime(
            t['transaction_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        multiplier = 1 if (t['booking_entry'] == 'DEBIT') else -1
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
                'amount': cur_flt(amount['value'], multiplier),
                'converted_from': cur_flt(
                    amount['converted_from_value'], multiplier),
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
                'link_amount': None,
                'order_id': t['order_id'],
                'item_codes': t['item_codes'],
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
                'amount': cur_flt(sale_value, multiplier),
                'converted_from': cur_flt(
                    sale_converted_from_value, multiplier),
                'currency': currency,
                'exchange_rate': exchange_rate,
                'link_doctype': None,
                'link_docname': None,
                'link_amount': None,
                'order_id': t['order_id'],
                'item_codes': t['item_codes'],
                'transaction': t
            })
            # Add fee entry (note opposite sign for fees)
            if fee_value:
                data.append({
                    'transaction_datetime': t_datetime,
                    'transaction_id': t['transaction_id'],
                    'transaction_type': t['transaction_type'] + ' FEES',
                    'amount': cur_flt(fee_value, -multiplier),
                    'converted_from': cur_flt(
                        fee_converted_from_value, -multiplier),
                    'currency': currency,
                    'exchange_rate': exchange_rate,
                    'link_doctype': None,
                    'link_docname': None,
                    'link_amount': None,
                    'order_id': t['order_id'],
                    'item_codes': t['item_codes'],
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
            'amount': cur_flt(p['amount']['value']),
            'converted_from': None,
            'currency': None,
            'exchange_rate': None,
            'link_doctype': None,
            'link_docname': None,
            'link_amount': None,
            'order_id': None,
            'item_codes': None,
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
                if len(gl_entries) == 1:
                    payment_value = gl_entries[0].credit - gl_entries[0].debit
                elif len(gl_entries) > 1:
                    frappe.throw(
                        f"""Transaction {t_id}
                        Sales invoice {sinv.name}
                        Wrong GL entries?"""
                    )
                else:
                    # Search for linked submitted Payment Entries
                    pe_list = frappe.get_all(
                        'Payment Entry Reference',
                        fields=['parent', 'allocated_amount'],
                        filters={
                            'docstatus': 1,
                            'reference_doctype': 'Sales Invoice',
                            'reference_name': sinv.name
                        }
                    )
                    amount = 0.0
                    for pe in pe_list:
                        if frappe.get_value('Payment Entry', pe.parent,
                                            'paid_to', ebay_bank):
                            amount += pe.allocated_amount
                            linked_documents.add(('Payment Entry', pe.parent))

                    payment_value = amount or None

            # Now add link
            t['link_doctype'] = 'Sales Invoice'
            t['link_docname'] = sinv.name
            t['link_amount'] = cur_flt(payment_value)
            if payment_value:
                linked_documents.add(('Sales Invoice', sinv.name))
        elif t_type in ('PAYOUT', 'TRANSFER'):
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
            # True payout should be positive, but transfer is 
            # typically negative
            if t_type == 'PAYOUT' and payout_value < 0:
                frappe.throw('Negative payout amount!')
            # Now add link
            t['link_doctype'] = 'Journal Entry'
            t['link_docname'] = je[0].name
            t['link_amount'] = cur_flt(payout_value)
            linked_documents.add(('Journal Entry', je[0].name))
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
            t['link_amount'] = submitted_sum or None
            for pinv_item in pinv_items:
                if pinv_item.docstatus != 1:
                    continue
                linked_documents.add(('Purchase Invoice Item', pinv_item.name))

    # Get any GL Entries that aren't accounted for
    gl_entries = frappe.get_all(
        'GL Entry',
        fields=['posting_date', 'debit', 'credit',
                'voucher_type', 'voucher_no'],
        filters={'account': ebay_bank}
    )
    gl_entries = [
        x for x in gl_entries
        if (start_date <= x.posting_date <= end_date)
    ]
    for gl_entry in gl_entries:
        amount = gl_entry.credit - gl_entry.debit
        meta = frappe.get_meta(gl_entry.voucher_type)
        if hasattr(meta, 'posting_date'):
            posting_date = frappe.get_value(
                gl_entry.voucher_type, gl_entry.voucher_no, 'posting_date')
        else:
            posting_date = gl_entry.posting_date
        if hasattr(meta, 'posting_time'):
            posting_time = frappe.get_value(
                gl_entry.voucher_type, gl_entry.voucher_no, 'posting_time')
            posting_time = (datetime.datetime.min + posting_time).time()
        else:
            posting_time = datetime.time.min
        posting_datetime = datetime.datetime.combine(
            posting_date,
            posting_time
        )
        if gl_entry.voucher_type == 'Purchase Invoice':
            # Check all PINVs are allocated
            all_pinv_items = frappe.get_all(
                'Purchase Invoice Item',
                fields=['name', 'amount'],
                filters={'parent': gl_entry.voucher_no}
            )
            linked_pinv_items = [
                x for x in all_pinv_items
                if ('Purchase Invoice Item', x.name) in linked_documents
            ]
            if len(linked_pinv_items) == len(all_pinv_items):
                continue  # if all PINVs allocated
            amount -= sum(x.amount for x in linked_pinv_items)
        else:
            key = (gl_entry.voucher_type, gl_entry.voucher_no)
            if key in linked_documents:
                # This document already considered
                continue
        data.append({
            'transaction_datetime': posting_datetime,
            'transaction_id': None,
            'transaction_type': 'UNMATCHED',
            'amount': None,
            'converted_from': None,
            'currency': None,
            'exchange_rate': None,
            'link_doctype': gl_entry.voucher_type,
            'link_docname': gl_entry.voucher_no,
            'link_amount': amount,
            'order_id': None,
            'item_codes': None
        })

    # Sort data into datetime order
    data.sort(key=operator.itemgetter('transaction_datetime'))

    # Remove the transaction/payout links
    for t in data:
        t.pop('transaction', None)
        t.pop('payout', None)

    # Convert item codes to string
    for t in data:
        item_codes = t['item_codes'] or []
        links = [frappe.utils.get_link_to_form('Item', x) for x in item_codes]
        t['item_codes'] = ', '.join(links)

    # Check for multiple refunds
    linked_refunds = defaultdict(list)
    for t in data:
        if t['transaction_type'] != 'REFUND':
            # Only do this for refunds
            continue
        if not (t['link_docname'] and t['link_amount']):
            # Don't fix unsubmitted links
            continue
        linked_refunds[t['link_docname']].append(t)
    for docname, t_list in linked_refunds.items():
        # Check for multiple links
        if len(t_list) <= 1:
            continue
        # Get link amount
        link_amounts = {t['link_amount'] for t in t_list}
        if len(link_amounts) != 1:
            raise ValueError('Link amounts are inconsistent!')
        link_amount = t_list[0]['link_amount']
        # Check sum of all links adds to sum of transaction amounts
        amount = sum(t['amount'] for t in t_list)
        if link_amount == amount:
            # Total works so set link_amount = amount
            for t in t_list:
                t['link_amount'] = t['amount']
                t['item_codes'] += '&nbsp;(partial allocation)'
        else:
            # Only allocate to first entry
            for t in t_list[1:]:
                t['link_amount'] == 0.0

    # Check if values are matched
    for t in data:
        t['matched'] = t['amount'] == t['link_amount']

    # If only showing mismatches, filter data
    if only_mismatches:
        data = [x for x in data if not x['matched']]

    for t in data:
        t['item_codes'] += '&nbsp;&nbsp;'

    return COLUMNS, data
