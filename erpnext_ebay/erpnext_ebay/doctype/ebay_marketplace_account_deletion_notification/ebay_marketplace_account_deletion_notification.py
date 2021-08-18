# -*- coding: utf-8 -*-
# Copyright (c) 2021, Ben Glazier and contributors
# For license information, please see license.txt

import base64
import datetime
import hashlib
import json

from werkzeug.wrappers import Response

import frappe
from frappe.model.document import Document

from erpnext_ebay.ebay_tokens import get_api


@frappe.whitelist(allow_guest=True)
def ebay_adn_endpoint(challenge_code=None, **kwargs):
    """Endpoint for the eBay Marketplace Account Deletion/Closure Notifications
    Either: provides acknowledgment for eBay of the endpoint
    Or:     accepts notifications and creates instances
                of eBay Marketplace Account Deletion Notification.
    """

    if challenge_code:
        # Respond with challengeResponse dict
        api_settings = frappe.get_single('eBay API Settings')
        verification_token = api_settings.get_password('adn_verification_token')
        endpoint = (
            frappe.utils.get_url('api/method/erpnext_ebay.ebay_adn_endpoint')
        )
        m = hashlib.sha256(
            (challenge_code + verification_token + endpoint).encode('utf-8')
        )
        return_data = {'challengeResponse': m.hexdigest()}

    elif 'notification' in kwargs and 'metadata' in kwargs:
        print('kwargs: ', kwargs)
        print('frappe.local.form_dict: ', frappe.local.form_dict)
        print('content: ')
        print(frappe.local.request.data)
        print(frappe.local.request.headers)
        metadata = kwargs['metadata']
        notification = kwargs['notification']
        data = notification.get('data')
        if not data:
            raise frappe.PermissionError()

        # Verify the request comes from eBay
        ebay_sig = frappe.local.request.headers.get('X-Ebay-Signature', None)
        if not ebay_sig:
            raise PermissionError()
        pki = base64.b64decode(ebay_sig.encode('utf-8'))
        # Get key_dict from cache, if it exists
        key_dict = frappe.cache().hget('erpnext_ebay_pki', pki)
        if not key_dict:
            api = get_api(sandbox=False)
            key_dict = api.commerce_notification_get_public_key(public_key_id=pki)
            frappe.cache().hset('erpnext_ebay', pki, key_dict)

        # Verify all expected fields exist
        for field in ('topic', 'schemaVersion', 'deprecated'):
            if field not in metadata:
                raise frappe.PermissionError()
        for field in ('notificationId', 'eventDate',
                      'publishDate', 'publishAttemptCount'):
            if field not in notification:
                raise frappe.PermissionError()
        for field in ('username', 'userId', 'eiasToken'):
            if field not in data:
                raise frappe.PermissionError()
        # Field conversions
        event_date = datetime.datetime.strptime(
            notification['eventDate'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        publish_date = datetime.datetime.strptime(
            notification['publishDate'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        publish_attempt_count = int(notification['publishAttemptCount'])

        # Add eBay Marketplace Account Deletion/Closure Notification
        adn_doc = frappe.get_doc({
            'doctype': 'eBay Marketplace Account Deletion Notification',
            'topic': metadata.get('topic'),
            'schema_version': metadata.get('schemaVersion'),
            'deprecated': metadata.get('deprecated'),
            'notification_id': notification.get('notificationId'),
            'event_date': event_date,
            'publish_date': publish_date,
            'publish_attempt_count': publish_attempt_count,
            'username': data.get('username'),
            'user_id': data.get('userId'),
            'eias_token': data.get('eiasToken')
        })
        #adn_doc.insert(ignore_permissions=True)
        return_data = ''
    else:
        raise frappe.PermissionError()

    response = Response()
    response.status_code = 200
    response.mimetype = 'application/json'
    response.charset = 'utf-8'
    response.data = json.dumps(return_data)
    return response


class eBayMarketplaceAccountDeletionNotification(Document):
    pass
