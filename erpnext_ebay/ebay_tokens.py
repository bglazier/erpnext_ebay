# -*- coding: utf-8 -*-

"""Methods to acquire and process eBay authorization tokens and consent.

This requires a 'live' server, which eBay is set up to direct the 'accept'
flow to, which then redirects the code to the desired server (which could
be a development server using 127.0.0.1, for example).

We also acquire and handle eBay public/private key pairs for
eBay Digital Signatures in this module.
"""

import base64
import datetime
import frappe
import html
import json
import secrets
import urllib.parse

import redo
import requests

from ebay_rest import API, DateTime as ERDateTime
from frappe.utils.password import get_decrypted_password

from erpnext_ebay.ebay_constants import (
    REDO_ATTEMPTS, REDO_SLEEPTIME, REDO_SLEEPSCALE, REDO_EXCEPTIONS,
    HOME_GLOBAL_ID, HOME_LANGUAGE
)


def oauth_basic_authentication(app_id, cert_id):
    """Get the basic authentication header string for OAuth2
    authentication based on App ID and Cert ID.
    """
    enc = base64.b64encode(f'{app_id}:{cert_id}'.encode('utf8'))
    return f'Basic {enc.decode()}'


@frappe.whitelist()
def generate_state_token(sandbox):
    """Generate a random state for eBay authorization flow"""
    sandbox = int(sandbox)
    roles = frappe.get_roles()
    if 'Administrator' not in roles and 'System Manager' not in roles:
        frappe.throw('Must be Administrator or System Manager!',
                     frappe.PermissionError)
    state_token = secrets.token_urlsafe(32)
    cache_name = 'EBAY_SANDBOX_AUTH' if sandbox else 'EBAY_PRODUCT_AUTH'
    expiry = frappe.utils.now_datetime() + datetime.timedelta(seconds=60)
    frappe.cache().hset(cache_name, state_token, expiry)
    return state_token


@frappe.whitelist(allow_guest=True)
def receive_consent_token():
    """Receive a consent token from eBay. This may not be for
    this server, so redirect it to the intended host.

    This will return HTTP 429 Too Many Requests if requested more
    than once every 5 seconds.

    WARNING - token must be checked for validity as there are no
    permission restrictions on this guest whitelisted method.
    """

    last_expiry = frappe.cache().hget('EBAY_AUTH_REDIRECT', 'expiry')
    if last_expiry and (frappe.utils.now_datetime() < last_expiry):
        frappe.throw('Too many eBay auth redirects',
                     exc=frappe.TooManyRequestsError)

    expiry = frappe.utils.now_datetime() + datetime.timedelta(seconds=5)
    frappe.cache().hset('EBAY_AUTH_REDIRECT', 'expiry', expiry)

    code = frappe.local.form_dict.get('code')
    state = frappe.local.form_dict.get('state')
    failed = False
    if not (code and state):
        frappe.throw('Invalid parameters')
    try:
        state_dict = json.loads(state)
    except Exception:
        failed = True
    if failed:
        frappe.throw('Invalid parameters')
    hostname = state_dict['hostname']
    method_url = "/api/method/erpnext_ebay.ebay_tokens.accept_consent_token"
    sandbox = 1 if state_dict['sandbox'] else 0
    state_token = urllib.parse.quote_plus(state_dict['state_token'])
    q_code = urllib.parse.quote_plus(code)
    base_url = f"{hostname}{method_url}"
    query_url = f"?sandbox={sandbox}&state_token={state_token}&code={q_code}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = f"{base_url}{query_url}"


@frappe.whitelist(allow_guest=True)
def accept_consent_token():
    """Receive the consent token once redirected by the 'live' server.

    Then check the token for validity, and exchange the authorization
    token for a user token and refresh token.

    WARNING - state token must be checked for validity as there are no
    permission restrictions on this guest whitelisted method.
    """

    # Get and check parameters
    sandbox = frappe.local.form_dict.get('sandbox')
    state_token = frappe.local.form_dict.get('state_token')
    code = frappe.local.form_dict.get('code')
    if not (state_token and code and (sandbox is not None)):
        frappe.throw('Invalid parameters!')
    sandbox = int(sandbox)

    # Check token is still valid
    cache_name = 'EBAY_SANDBOX_AUTH' if sandbox else 'EBAY_PRODUCT_AUTH'
    expiry = frappe.cache().hget(cache_name, state_token)
    if not expiry:
        frappe.throw('Invalid parameters!')
    elif expiry <= frappe.utils.now_datetime():
        return frappe.respond_as_web_page(
            title='Token expired',
            http_status_code=403,
            html=f"""
                <p>This token has expired. Please repeat the
                authorization process.</p>""",
            success=False
        )
    # Clear token validity
    frappe.cache().hdel(cache_name, state_token)

    # Set prefix and URL for gaining user refresh token later
    if sandbox:
        url = 'https://api.sandbox.ebay.com/identity/v1/oauth2/token'
        prefix = 'sandbox'
    else:
        url = 'https://api.ebay.com/identity/v1/oauth2/token'
        prefix = 'production'

    # Load API settings document
    api_settings = frappe.get_single('eBay API Settings')
    app_id = api_settings.get(f'{prefix}_app_id')
    cert_id = api_settings.get_password(f'{prefix}_cert_id')
    ru_name = api_settings.get(f'{prefix}_ru_name')

    # Exchange authorization code for eBay user token and update
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': oauth_basic_authentication(app_id, cert_id)
    }

    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': ru_name
    }

    r = requests.post(url, headers=headers, data=data)

    # Process response
    if not r.ok:
        frappe.throw('Invalid parameters!')

    user_access = r.json()
    if user_access['token_type'] != 'User Access Token':
        frappe.throw('Invalid parameters!')
    refresh_token = user_access['refresh_token']
    refresh_expiry = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=user_access['refresh_token_expires_in'])
    )

    # Store authorization token in eBay API Settings
    api_settings.set(f'{prefix}_refresh_token', refresh_token)
    api_settings.set(f'{prefix}_refresh_expiry', refresh_expiry)
    api_settings.save(ignore_permissions=True)
    frappe.db.commit()

    return frappe.respond_as_web_page(
        title='Consent received',
        html=f"""
            <p>Authorization successfully completed.</p>
            <p>It's now safe to close the browser window/tab.</p>""",
        success=True
    )


@frappe.whitelist()
def create_new_key_pair(sandbox):
    """Create a new key pair.

    Will throw an error if there is a current valid in-date key pair.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay API Settings', 'write'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    prefix = 'sandbox' if sandbox else 'production'
    dt = 'eBay API Settings'

    sandbox = int(sandbox)

    api = get_api(sandbox, ignore_key_pair=True)

    if api._key_pair_token._has_valid_key(api):
        frappe.msgprint('Current key pair is valid')
        return

    key = api.get_digital_signature_key(create_new=True)
    api_doc = frappe.get_single('eBay API Settings')
    expiration_time = ERDateTime.from_string(key['expiration_time'])
    setattr(api_doc, f'{prefix}_private_key', key['private_key'])
    setattr(api_doc, f'{prefix}_key_jwe', key['jwe'])
    setattr(api_doc, f'{prefix}_signing_key_id', key['signing_key_id'])
    setattr(api_doc, f'{prefix}_key_expiration', expiration_time)
    api_doc.save()

@redo.retriable(attempts=REDO_ATTEMPTS, sleeptime=REDO_SLEEPTIME,
                sleepscale=REDO_SLEEPSCALE, retry_exceptions=REDO_EXCEPTIONS)
def _get_api(application, user, header, key_pair, digital_signatures,
             *args, **kwargs):
    """Get and return an API. Retriable function."""

    return API(application=application, user=user, header=header,
               key_pair=key_pair, digital_signatures=digital_signatures)


def get_api(sandbox=False, *args, **kwargs):
    """Get an ebay_rest API loaded with credentials."""

    MANDATORY_APP = ('app_id', 'cert_id', 'redirect_uri')

    prefix = 'sandbox' if sandbox else 'production'
    dt = 'eBay API Settings'

    ignore_key_pair = kwargs.pop('ignore_key_pair', False)

    # Application tokens
    application = {
        'app_id': frappe.get_value(dt, dt, f'{prefix}_app_id'),
        'cert_id': get_decrypted_password(dt, dt, f'{prefix}_cert_id',
                                          raise_exception=False),
        #'dev_id': None,  # Don't need dev_id
        'redirect_uri': frappe.get_value(dt, dt, f'{prefix}_ru_name')
    }

    if not all(application[x] for x in MANDATORY_APP):
        frappe.throw(f'Missing API application parameters for {prefix}!')

    # User tokens
    refresh_token = get_decrypted_password(dt, dt, f'{prefix}_refresh_token',
                                           raise_exception=False)
    refresh_token_expiry = frappe.get_value(dt, dt, f'{prefix}_refresh_expiry')
    if not (refresh_token and refresh_token_expiry):
        frappe.throw(f'Re-authorize eBay {prefix}; token missing')

    refresh_token_expiry = (
        frappe.utils.get_datetime(refresh_token_expiry)
        - datetime.timedelta(minutes=5)
    ).astimezone(datetime.timezone.utc)

    user = {
        'email_or_username': 'FAIL',  # Have to pass this
        'password': 'FAIL',  # Have to pass this
        'scopes': frappe.get_value(dt, dt, f'{prefix}_scopes').strip().split(),
        'refresh_token': refresh_token,
        'refresh_token_expiry': ERDateTime.to_string(refresh_token_expiry)
    }
    if not user['scopes']:
        frappe.throw(f'Missing API user parameters (scopes) for {prefix}!')

    # Header
    header = {
        'accept_language': kwargs.get('accept_language', HOME_LANGUAGE),
        'content_language': kwargs.get('content_language', HOME_LANGUAGE),
        'marketplace_id': kwargs.get('marketplace_id', HOME_GLOBAL_ID)
    }

    # Digital signature public/private key pair
    private_key = get_decrypted_password(dt, dt, f'{prefix}_private_key',
                                         raise_exception=False)
    signing_key_id = frappe.get_value(dt, dt, f'{prefix}_signing_key_id')
    jwe = frappe.get_value(dt, dt, f'{prefix}_key_jwe')
    expiration_time = frappe.get_value(dt, dt, f'{prefix}_key_expiration')
    if expiration_time:
        expiration_time = ERDateTime.to_string(
            frappe.utils.get_datetime(expiration_time)
        )

    if not (private_key and signing_key_id):
        if not ignore_key_pair:
            frappe.throw(f'Need to get new private/public key pair!')

    # Key pair
    key_pair = {
        'private_key': private_key or '',
        'signing_key_id': signing_key_id or '',
        'jwe': jwe or '',
        'expiration_time': expiration_time or ''
    }

    api = _get_api(application, user, header, key_pair,
                   digital_signatures=True, *args, **kwargs)

    # Load and save the jwe public key and expiration time, if we did not
    # have these (unless ignoring the key pair)
    if (not ignore_key_pair) and not (jwe or expiration_time):
        key = api.get_digital_signature_key(create_new=False)
        expiration_time = ERDateTime.from_string(key['expiration_time'])
        frappe.set_value(dt, dt, f'{prefix}_key_expiration', expiration_time)
        frappe.set_value(dt, dt, f'{prefix}_key_jwe', key['jwe'])

    return api
