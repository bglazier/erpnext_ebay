# Copyright (c) 2025, Ben Glazier and contributors
# For license information, please see license.txt

import datetime

import frappe

from erpnext_ebay.ebay_requests_rest import get_api_usage


COLUMNS = [
    {
        'fieldname': 'api_context',
        'label': 'API Context',
        'fieldtype': 'Data',
        'width': 120
    },
    {
        'fieldname': 'api_name',
        'label': 'API Name',
        'fieldtype': 'Data',
        'width': 150
    },
    {
        'fieldname': 'api_version',
        'label': '',
        'fieldtype': 'Data',
        'width': 40
    },
    {
        'fieldname': 'call_name',
        'label': 'Call name',
        'fieldtype': 'Data',
        'width': 250
    },
    {
        'fieldname': 'remaining',
        'label': 'Remaining',
        'fieldtype': 'Int',
        'width': 100
    },
    {
        'fieldname': 'limit',
        'label': 'Limit',
        'fieldtype': 'Int',
        'width': 100
    },
    {
        'fieldname': 'reset_datetime',
        'label': 'Reset time (UTC)',
        'fieldtype': 'Datetime',
        'width': 240
    },
    {
        'fieldname': 'time_window',
        'label': 'Window (hours)',
        'fieldtype': 'Float',
        'width': 150
    }
]


def execute(filters=None):
    """Get eBay usage data from the Developer Analytics API and display it."""
    table_data = []

    usage_data = get_api_usage()['rate_limits']

    for context_dict in usage_data:
        for resource in context_dict['resources']:
            if not resource.get('rates'):
                # There are not always rates
                table_data.append({
                    'api_context': context_dict['api_context'],
                    'api_name': context_dict['api_name'],
                    'api_version': context_dict['api_version'],
                    'call_name': resource['name'],
                })
                continue
            for rate in resource['rates']:
                reset_datetime = datetime.datetime.strptime(
                    rate['reset'][:-1] + 'UTC', '%Y-%m-%dT%H:%M:%S.%f%Z'
                )
                table_data.append({
                    'api_context': context_dict['api_context'],
                    'api_name': context_dict['api_name'],
                    'api_version': context_dict['api_version'],
                    'call_name': resource['name'],
                    'limit': rate['limit'],
                    'remaining': rate['remaining'],
                    'reset_datetime': reset_datetime,
                    'time_window': rate['time_window'] / 3600
                })

    return COLUMNS, table_data
