"""A module of eBay constants"""

# Ebay PaymentMethods and their descriptions - TODO write descriptions!
PAYMENT_METHODS = (('AmEx', None),
                   ('CashInPerson', None),
                   ('CashOnPickup', None),
                   ('CCAccepted', None),
                   ('COD', None),
                   ('CODPrePayDelivery', None),
                   ('CreditCard', None),
                   ('Diners', None),
                   ('DirectDebit', None),
                   ('Discover', None),
                   ('ELV', None),
                   ('Escrow', None),
                   ('IntegratedMerchantCreditCard', None),
                   ('LoanCheck', None),
                   ('MOCC', None),
                   ('MoneyXferAccepted', None),
                   ('MoneyXferAcceptedInCheckout', None),
                   ('None', None),
                   ('Other', None),
                   ('OtherOnlinePayments', None),
                   ('PaisaPayAccepted', None),
                   ('PaisaPayEscrow', None),
                   ('PaisaPayEscrowEMI', None),
                   ('PaymentSeeDescription', None),
                   ('PayOnPickup', None),
                   ('PayPal', None),
                   ('PayPalCredit', None),
                   ('PayUponInvoice', None),
                   ('PersonalCheck', None),
                   ('PostalTransfer', None),
                   ('PrePayDelivery', None),
                   ('VisaMC', None))

# A list of attributes that are not supported (probably because they
# are an array type)
FEATURES_NOT_SUPPORTED = ('GalleryFeaturedDurations',
                          'StoreOwnerExtendedListingDurations')

# A list of either useful or common attributes (to minimise use of
# the 'extra' table) or complex attributes handled separately
FEATURES_PRIMARY_COLUMNS = ('CategoryID', 'ConditionValues',
                            'ConditionHelpURL', 'CompatibleVehicleType',
                            'GlobalShippingEnabled', 'MaxFlatShippingCost',
                            'PaymentMethods', 'ExpressEnabled')
# Listing code tokens
days = (1, 3, 5, 7, 10, 14, 21, 28, 30, 60, 90, 120)
low_num = ['One', 'Two', 'Three', 'Four', 'Five',
           'Six', 'Seven', 'Eight', 'Nine']
tokens = ['Days_' + str(n) for n in days]
descriptions = ['{}-day listing'.format(
    low_num[n-1] if n < len(low_num) else str(n))
    for n in days]
LISTING_CODE_TOKENS = (tuple(zip(tokens, days, descriptions))
                       + (('GTC', None, "Good 'Til Cancelled"),))
del low_num, days, tokens, descriptions