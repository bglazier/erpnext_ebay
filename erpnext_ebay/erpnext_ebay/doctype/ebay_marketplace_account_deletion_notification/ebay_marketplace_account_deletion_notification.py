# -*- coding: utf-8 -*-
# Copyright (c) 2021, Ben Glazier and contributors
# For license information, please see license.txt

import base64
import datetime
import ecdsa
import hashlib
import json

from werkzeug.wrappers import Response

import frappe
from frappe.model.document import Document

from erpnext_ebay.ebay_tokens import get_api


def fix_public_key(str_key):
    """eBay public keys are delivered in the format:
    -----BEGIN PUBLIC KEY-----key-----END PUBLIC KEY-----
    which is missing critical newlines around the key for ecdsa to
    process it.
    This adds those newlines and converts to bytes.
    """
    return (
        str_key
        .replace('KEY-----', 'KEY-----\n')
        .replace('-----END', '\n-----END')
        .encode('utf-8')
    )


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
        metadata = kwargs['metadata']
        notification = kwargs['notification']
        data = notification.get('data')
        if not data:
            raise frappe.PermissionError()

        # Verify the request comes from eBay
        ebay_sig = frappe.local.request.headers.get('X-Ebay-Signature', None)
        if not ebay_sig:
            raise PermissionError()
        sig_dict = json.loads(base64.b64decode(ebay_sig))
        kid = sig_dict['kid']
        # Get key_dict from cache, if it exists
        key_dict = frappe.cache().hget('erpnext_ebay_pki', kid)
        if not key_dict:
            api = get_api(sandbox=False)
            key_dict = api.commerce_notification_get_public_key(
                public_key_id=kid)
            frappe.cache().hset('erpnext_ebay', kid, key_dict)
        if key_dict['algorithm'] != 'ECDSA':
            raise NotImplementedError('Only ECDSA implemented!')
        if key_dict['digest'] != 'SHA1':
            raise NotImplementedError('Only SHA1 digest implemented!')
        # Gather for verification and verify
        public_key = fix_public_key(key_dict['key'])
        message = frappe.local.request.data
        signature = base64.b64decode(sig_dict['signature'])
        vk = ecdsa.VerifyingKey.from_pem(public_key, hashfunc=hashlib.sha1)
        try:
            vk.verify(
                signature, message, sigdecode=ecdsa.util.sigdecode_der
            )
        except ecdsa.BadSignatureError:
            # Bad signature
            raise PermissionError()

        # Verify all expected fields exist
        for field in ('topic', 'schemaVersion', 'deprecated'):
            if not (field in metadata and metadata[field]):
                raise frappe.PermissionError()
        for field in ('notificationId', 'eventDate',
                      'publishDate', 'publishAttemptCount'):
            if not (field in notification and notification[field]):
                raise frappe.PermissionError()
        for field in ('username', 'userId', 'eiasToken'):
            if not (field in data and data[field]):
                raise frappe.PermissionError()

        # Blank, but successful return
        return_data = ''

        # Check for matching customer, and if so record
        customers = frappe.get_all(
            'Customer',
            filters={'ebay_user_id': data['username']}
        )
        if customers:
            # Only record if we have a matching customer

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
                'topic': metadata['topic'],
                'schema_version': metadata['schemaVersion'],
                'deprecated': metadata['deprecated'],
                'notification_id': notification['notificationId'],
                'event_date': event_date,
                'publish_date': publish_date,
                'publish_attempt_count': publish_attempt_count,
                'username': data['username'],
                'user_id': data['userId'],
                'eias_token': data['eiasToken']
            })
            adn_doc.insert(ignore_permissions=True)
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
