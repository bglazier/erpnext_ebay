"""A module of eBay constants"""

# Assumed maximum length of eBay attributes and values
EBAY_ATTR_LEN = 100
EBAY_ATTR_LEN_STR = str(EBAY_ATTR_LEN)
EBAY_VALUE_LEN = 1000
EBAY_VALUE_LEN_STR = str(EBAY_VALUE_LEN)

# eBay PaymentMethods and their descriptions - TODO write descriptions!
PAYMENT_METHODS = {'AmEx': None,
                   'CashInPerson': None,
                   'CashOnPickup': None,
                   'CCAccepted': None,
                   'COD': None,
                   'CODPrePayDelivery': None,
                   'CreditCard': None,
                   'Diners': None,
                   'DirectDebit': None,
                   'Discover': None,
                   'ELV': None,
                   'Escrow': None,
                   'IntegratedMerchantCreditCard': None,
                   'LoanCheck': None,
                   'MOCC': None,
                   'MoneyXferAccepted': None,
                   'MoneyXferAcceptedInCheckout': None,
                   'None': None,
                   'Other': None,
                   'OtherOnlinePayments': None,
                   'PaisaPayAccepted': None,
                   'PaisaPayEscrow': None,
                   'PaisaPayEscrowEMI': None,
                   'PaymentSeeDescription': None,
                   'PayOnPickup': None,
                   'PayPal': None,
                   'PayPalCredit': None,
                   'PayUponInvoice': None,
                   'PersonalCheck': None,
                   'PostalTransfer': None,
                   'PrePayDelivery': None,
                   'VisaMC': None}

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
LISTING_TYPES_SUPPORTED = ('Chinese', 'FixedPriceItem')

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
                       + (('GTC', None, "Good 'Til Cancelled"),))
LISTING_DURATION_TOKEN_DICT = {
    x[0]: (x[1], x[2]) for x in LISTING_DURATION_TOKENS}
del low_num, days, tokens, descriptions