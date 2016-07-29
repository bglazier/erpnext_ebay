"""Functions to generate eBay listings."""

from __future__ import unicode_literals
from __future__ import print_function

import urllib

import frappe
from frappe import msgprint

from ebay_requests import verify_add_item


@frappe.whitelist()
def test_listing_item(doc_name):
    """Test the eBay listing document using VerifyAddItem.

    If no errors are found, return 'true' (string). Otherwise,
    return 'false'.
    """
    print('doc_name: ', doc_name)
    msgprint('doc_name: '+doc_name)
    listing_doc = frappe.get_doc("eBay Listing", doc_name)
    listing_dict = construct_ebay_listing(listing_doc)

    ret_dict = verify_add_item(listing_dict)

    return 'false'


def construct_ebay_listing(listing_doc):
    """Convert a list document to a dictionary for the ebaysdk module"""

    listing_dict = {
        "Item": {
            "Title": "Harry Potter and the Philosopher's Stone",
            "Description": "This is the first book in the Harry Potter series. In excellent condition!",
            "PrimaryCategory": {"CategoryID": "171220"},
            "StartPrice": "1.0",
            "CategoryMappingAllowed": "true",
            "Country": "GB",
            "ConditionID": "2750",
            "ConditionDescription": "In good nick, innit?",
            "Currency": "GBP",
            "DispatchTimeMax": "3",
            "ListingDuration": "Days_7",
            "ListingType": "Chinese",
            "PaymentMethods": "PayPal",
            "PayPalEmailAddress": "tkeefdddder@gmail.com",
            "PictureDetails": {"PictureURL": "http://lorempixel.com/output/nature-q-c-400-400-8.jpg"},
            "PostalCode": "EX4 5HE",
            "Quantity": "1",
            "ReturnPolicy": {
                "ReturnsAcceptedOption": "ReturnsAccepted",
                "ReturnsWithinOption": "Days_30",
                "Description": "If you are not satisfied, return the book for refund.",
                "ShippingCostPaidByOption": "Buyer"
            },
            "ShippingDetails": {
                "ShippingType": "Flat",
                "ShippingServiceOptions": {
                    "ShippingServicePriority": "1",
                    "ShippingService": "UK_Parcelforce24",
                    "ShippingServiceCost": "2.50"
                }
            },
            "Site": "UK"
        }
    }

    return listing_dict
