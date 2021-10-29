"""A module of eBay constants"""

import frappe

# Redo parameters for retrying transactions
REDO_ATTEMPTS = 3
REDO_SLEEPTIME = 3.0
REDO_SLEEPSCALE = 1.5

# Maximum number of eBay images per listing
MAX_EBAY_IMAGES = 12

# Assumed maximum length of eBay attributes and values
EBAY_ATTR_LEN = 100
EBAY_ATTR_LEN_STR = str(EBAY_ATTR_LEN)
EBAY_VALUE_LEN = 1000
EBAY_VALUE_LEN_STR = str(EBAY_VALUE_LEN)

HOME_SITE_ID = 3
HOME_GLOBAL_ID = 'EBAY_GB'
HOME_MARKETPLACE_ID = 'EBAY_GB'

# eBay Site IDs
EBAY_SITE_IDS = {
    0: 'US',
    2: 'Canada (English)',
    3: 'UK',
    15: 'Australia',
    16: 'Austria',
    23: 'Belgium (French)',
    71: 'France',
    77: 'Germany',
    100: 'Motors',
    101: 'Italy',
    123: 'Belgium (Dutch)',
    146: 'Netherlands',
    186: 'Spain',
    193: 'Switzerland',
    201: 'Hong Kong',
    203: 'India',
    205: 'Ireland',
    207: 'Malaysia',
    210: 'Canada (French)',
    211: 'Philippines',
    212: 'Poland',
    216: 'Singapore'
}

EBAY_SITE_NAMES = {name: siteid for siteid, name in EBAY_SITE_IDS.items()}
HOME_SITE_NAME = EBAY_SITE_IDS[HOME_SITE_ID]

EBAY_TRANSACTION_SITE_IDS = {
    0: 'US',
    2: 'Canada',
    3: 'UK',
    15: 'Australia',
    16: 'Austria',
    23: 'Belgium_French',
    71: 'France',
    77: 'Germany',
    100: 'eBayMotors',
    101: 'Italy',
    123: 'Belgium_Dutch',
    146: 'Netherlands',
    186: 'Spain',
    193: 'Switzerland',
    201: 'HongKong',
    203: 'India',
    205: 'Ireland',
    207: 'Malaysia',
    210: 'CanadaFrench',
    211: 'Phillipines',
    212: 'Poland',
    215: 'Russia',
    216: 'Singapore'
}

EBAY_TRANSACTION_SITE_NAMES = {
    name: siteid for siteid, name in EBAY_TRANSACTION_SITE_IDS.items()}
HOME_TRANSACTION_SITE_NAME = EBAY_TRANSACTION_SITE_IDS[HOME_SITE_ID]

# eBay Site domains
EBAY_SITE_DOMAINS = {
    0: 'com',
    2: 'ca',
    3: 'co.uk',
    15: 'com.au',
    16: 'at',
    23: 'be',
    71: 'fr',
    77: 'de',
    100: 'com',
    101: 'it',
    123: 'be',
    146: 'nl',
    186: 'es',
    193: 'ch',
    201: 'com.hk',
    203: '.in',
    205: '.ie',
    207: 'com.my',
    210: '.ca',
    211: 'ph',
    212: 'pl',
    216: 'com.sg'
}

# eBay Marketplace IDs
EBAY_MARKETPLACE_IDS = {
    'EBAY_US': 'United States',
    'EBAY_AT': 'Austria',
    'EBAY_AU': 'Australia',
    'EBAY_BE': 'Belgium',
    'EBAY_CA': 'Canada',
    'EBAY_CH': 'Switzerland',
    'EBAY_DE': 'Germany',
    'EBAY_ES': 'Spain',
    'EBAY_FR': 'France',
    'EBAY_GB': 'United Kingdom',
    'EBAY_HK': 'Hong Kong',
    'EBAY_IE': 'Ireland',
    'EBAY_IN': 'India',
    'EBAY_IT': 'Italy',
    'EBAY_MY': 'Malaysia',
    'EBAY_NL': 'Netherlands',
    'EBAY_PH': 'Philippines',
    'EBAY_PL': 'Poland',
    'EBAY_SG': 'Singapore',
    'EBAY_TH': 'Thailand',
    'EBAY_TW': 'Taiwan',
    'EBAY_VN': 'Vietnam',
    'EBAY_MOTORS_US': 'United States (Motors)'
}


EBAY_GLOBAL_SITE_IDS = {
    0: 'EBAY-US',
    2: 'EBAY-CA',
    3: 'EBAY-GB',
    15: 'EBAY-AU',
    16: 'EBAY-AT',
    23: 'EBAY-FRBE',
    71: 'EBAY-FR',
    77: 'EBAY-DE',
    100: 'EBAY-MOTOR',
    101: 'EBAY-IT',
    123: 'EBAY-NLBE',
    146: 'EBAY-NL',
    186: 'EBAY-ES',
    193: 'EBAY-CH',
    201: 'EBAY-HK',
    203: 'EBAY-IN',
    205: 'EBAY-IE',
    207: 'EBAY-MY',
    210: 'EBAY-FRCA',
    211: 'EBAY-PH',
    212: 'EBAY-PL',
    216: 'EBAY-SG'
}

EBAY_MARKETPLACE_SITE_IDS = {
    'EBAY_AT': 16,
    'EBAY_AU': 15,
    'EBAY_BE': 23,
    'EBAY_CA': 2,
    'EBAY_CH': 193,
    'EBAY_CN': None,
    'EBAY_CZ': None,
    'EBAY_DE': 77,
    'EBAY_DK': None,
    'EBAY_ES': 186,
    'EBAY_FI': None,
    'EBAY_FR': 71,
    'EBAY_GB': 3,
    'EBAY_GR': None,
    'EBAY_HK': 201,
    'EBAY_HU': None,
    'EBAY_ID': None,
    'EBAY_IE': 205,
    'EBAY_IL': None,
    'EBAY_IN': 203,
    'EBAY_IT': 101,
    'EBAY_JP': None,
    'EBAY_MY': 207,
    'EBAY_NL': 146,
    'EBAY_NO': None,
    'EBAY_NZ': None,
    'EBAY_PE': None,
    'EBAY_PH': 211,
    'EBAY_PL': 212,
    'EBAY_PR': None,
    'EBAY_PT': None,
    'EBAY_RU': 215,
    'EBAY_SE': None,
    'EBAY_SG': 216,
    'EBAY_TH': None,
    'EBAY_TW': None,
    'EBAY_US': 0,
    'EBAY_VN': None,
    'EBAY_ZA': None,
    'EBAY_MOTORS_US': 100
}

# eBay PaymentMethods and their descriptions
PAYMENT_METHODS = {'AmEx': 'American Express',
                   'CashInPerson': 'Cash in person (US/CA Motors only)',
                   'CashOnPickup': 'Payment on delivery',
                   'CCAccepted': 'Credit card',
                   'COD': 'Cash on delivery (not US/CA/UK)',
                   'CODPrePayDelivery': '(reserved)',
                   'CreditCard': 'Credit card (eBay Now only)',
                   'Diners': 'Diners Club Card (Cybersource Gateway sellers)',
                   'DirectDebit': 'Debit card (eBay Now only)',
                   'Discover': 'Discover card',
                   'ELV': 'Elektronisches Lastschriftverfahren (obselete)',
                   'Escrow': '(reserved)',
                   'IntegratedMerchantCreditCard':
                       'Credit card (payment gateway)',
                   'LoanCheck': 'Loan check (US/CA Motors only)',
                   'MOCC': "Money order/cashiers' cheque",
                   'MoneyXferAccepted': 'Money/bank transfer',
                   'MoneyXferAcceptedInCheckout':
                       'Money/bank transfer (displayed at checkout)',
                   'None': 'No payment method specified',
                   'Other': 'Other',
                   'OtherOnlinePayments': 'Other online payment',
                   'PaisaPayAccepted': 'PaisaPay (India only)',
                   'PaisaPayEscrow': 'PaisaPay Escrow (India only)',
                   'PaisaPayEscrowEMI':
                       'PaisaPay Escrow equal monthly installments '
                       + '(India only)',
                   'PaymentSeeDescription':
                       'See description for payment details',
                   'PayOnPickup': 'Pay on pickup',
                   'PayPal': 'Paypal',
                   'PayPalCredit': 'Paypal credit card',
                   # PayUponInvoice is not a valid option for listing
                   'PayUponInvoice': 'Pay Upon Invoice (DE only)',
                   'PersonalCheck': 'Personal cheque',
                   'PostalTransfer': '(reserved)',
                   'PrePayDelivery': '(reserved)',
                   'VisaMC': 'Visa/Mastercard'}

PAYMENT_METHODS_SUPPORTED = ('AmEx', 'CashOnPickup', 'CCAccepted',
                             'CreditCard', 'Discover',
                             'IntegratedMerchantCreditCard', 'MOCC',
                             'MoneyXferAccepted', 'None', 'Other',
                             'OtherOnlinePayments', 'PaymentSeeDescription',
                             'PayPal', 'PayPalCredit', 'PersonalCheck',
                             'VisaMC')

# eBay listing types, and their descriptions
LISTING_TYPES = {'AdType': 'Advertisement',
                 'Auction': None,
                 'Chinese': 'Auction',
                 'Live': None,
                 'FixedPriceItem': 'Buy It Now',
                 'LeadGeneration': 'Advertisement',
                 'PersonalOffer': 'Second Chance Offer',
                 'StoresFixedPrice': 'Buy It Now (eBay Store)'}
# Listing types we use - these should be permissible site-wide as there is
# no checking by category for listing types
LISTING_TYPES_SUPPORTED = ('Chinese', 'FixedPriceItem', 'StoresFixedPrice')

# Feature columns

# Not supported (usually because they are array types)
FEATURES_NOT_SUPPORTED = ('GalleryFeaturedDurations',
                          'StoreOwnerExtendedListingDurations')
# The extra columns produced for ListingDuration
LISTING_DURATION_COLUMNS = tuple(
    'ListingDuration' + x for x in LISTING_TYPES)
# The columns chosen to be stored in the base, rather than extra, table
_BASE_COLUMNS = (
    'CompatibleVehicleType', 'ExpressEnabled', 'GlobalShippingEnabled',
    'MaxFlatShippingCost', 'MaxFlatShippingCostCurrency', 'ConditionEnabled')
# Features removed to separate tables
FEATURES_REMOVED = (
    'ConditionValues', 'ListingDurations', 'PaymentMethods')
# Extra columns to the base table
FEATURES_BASE_ADDED = ('ConditionHelpURL',)

# Columns of the basic features table
# NOTE - changes here should be matched by changes to the SQL query creating
# the table
FEATURES_BASE_COLUMNS = (('CategoryID',)
                         + LISTING_DURATION_COLUMNS
                         + _BASE_COLUMNS
                         + FEATURES_BASE_ADDED)

# These FeatureDefinitions are not stored in the 'extra' table
# For now this includes 'complicated' features like ListingDurations
FEATURES_NOT_EXTRA = (('CategoryID',)
                      + FEATURES_REMOVED
                      + _BASE_COLUMNS)

# Listing code tokens
days = (1, 3, 5, 7, 10, 14, 21, 28, 30, 60, 90, 120)
low_num = ['One', 'Two', 'Three', 'Four', 'Five',
           'Six', 'Seven', 'Eight', 'Nine']
tokens = ['Days_' + str(n) for n in days]
descriptions = ['{}-day listing'.format(
    low_num[n-1] if n < len(low_num) else str(n))
    for n in days]
LISTING_DURATION_TOKENS = (tuple(zip(tokens, days, descriptions))
                           + (('GTC', None, 'GTC'),))
LISTING_DURATION_TOKEN_DICT = {
    x[0]: (x[1], x[2]) for x in LISTING_DURATION_TOKENS}
del low_num, days, tokens, descriptions

MAX_AUTOPAY_PRICE = 2500.0


@frappe.whitelist()
def get_ebay_constants():
    """Return eBay constants such as the supported listing types"""
    return_dict = {}
    return_dict['listing_type'] = [
        {'value': x, 'label': LISTING_TYPES[x]}
        for x in LISTING_TYPES_SUPPORTED]

    return_dict['payment_methods'] = [
        {'value': x,
         'label': PAYMENT_METHODS[x]}
        for x in PAYMENT_METHODS_SUPPORTED]

    return_dict['MAX_AUTOPAY_PRICE'] = MAX_AUTOPAY_PRICE

    return return_dict
