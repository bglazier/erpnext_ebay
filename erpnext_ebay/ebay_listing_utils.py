"""Functions to generate eBay listings."""

from __future__ import unicode_literals
from __future__ import print_function

import ast
import os
import pickle
import frappe
from frappe import msgprint,_

from ebay_requests import (sandbox_listing_testing,
                           get_categories_version,
                           get_categories)

categories_cache_file = 'erpnext_ebay.categories.pkl'


def cache_ebay_categories():
    """Check, and update, the stored cache of eBay categories is current"""

    cache_version = frappe.db.get_value(
        'eBay Manager Settings', filters=None,
        fieldname='ebay_categories_cache_version')
    # Check eBay cache file exists
    cache_file = os.path.join(frappe.utils.get_site_path(),
                              categories_cache_file)
    cache_file_exists = os.path.isfile(cache_file)

    # Check eBay API for current categories version
    ebay_version = get_categories_version()
    if (not cache_file_exists) or (cache_version != ebay_version):
        # Load new eBay categories
        new_version, new_categories, max_level = get_categories()
        frappe.db.set_value('eBay Manager Settings', None,
                            'ebay_categories_cache_version',
                            new_version)
        frappe.db.set_value('eBay Manager Settings', None,
                            'ebay_categories_cache_maximum_level',
                            max_level)

        # Pickle the new categories to a cache file
        with open(cache_file, 'wb') as f:
            pickle.dump(new_categories, f, pickle.HIGHEST_PROTOCOL)


def load_ebay_categories_cache():
    """Return the categories stored in the eBay categories cache"""
    cache_file = os.path.join(frappe.utils.get_site_path(),
                              categories_cache_file)
    with open(cache_file, 'rb') as f:
        return pickle.load(f)


def get_ebay_categories(ebay_categories, category_stack):
    """Return the category names for the category stack"""
    categories = []
    if not category_stack:
        return categories
    # Top-level categories
    top_level = ebay_categories['TopLevel']
    categories.append([(x['CategoryID'],
                        x['CategoryName']) for x in top_level])
    # Loop over the categories in the top level, and find our top-level category
    for cat in top_level:
        if int(cat['CategoryID']) == int(category_stack[0]):
            parent_cat = cat
            break
    else:
        raise ValueError('No such category found!')

    # Append the children of our top-level category to the categories list
    categories.append([(x['CategoryID'],
                        x['CategoryName']) for x in parent_cat['Children']])

    # Proceed for each new level in turn
    for i, parent_cat_id in enumerate(category_stack[1:], start=1):
        if parent_cat_id==0:
            # Run out of selected categories
            if parent_cat:
                # One last level below last selected category
                categories.append(
                    [(x['CategoryID'],
                      x['CategoryName']) for x in parent_cat['Children']])
                parent_cat = None
            else:
                # Beyond the last level we need options for
                categories.append([])
            continue
        for cat in parent_cat['Children']:
            if int(cat['CategoryID']) == int(parent_cat_id):
                parent_cat = cat
                break
        else:
            raise ValueError('No such category found!')
        # Add the children for our category on this level
        categories.append([(x['CategoryID'],
                            x['CategoryName']) for x in parent_cat['Children']])

    # Note that this will return len(category_stack) + 1 rows
    return categories


@frappe.whitelist()
def client_get_ebay_categories(category_stack):
    """Return category options at all levels for category_stack"""

    # Frappe passes our lists as a string, so convert back to list
    if isinstance(category_stack, basestring):
        category_stack = ast.literal_eval(category_stack)

    # Load the eBay cache
    cache_ebay_categories()
    ebay_categories = load_ebay_categories_cache()

    # Get full list of category options from top level to category level
    cat_options_stack = get_ebay_categories(ebay_categories, category_stack)

    # Format the category options stack ready for the Javascript select options
    for cat_options in cat_options_stack:
        if cat_options:
            for i, cat_tuple in enumerate(cat_options):
                cat_options[i] = {'value': cat_tuple[0],
                                  'label': cat_tuple[1]}
    return cat_options_stack


@frappe.whitelist()
def client_update_ebay_categories(category_level, category_stack):
    """Category at category_level has changed. Return new options at
    category_level+1.
    """

    # Frappe passes our lists as a string, so convert back to list
    if isinstance(category_stack, basestring):
        category_stack = ast.literal_eval(category_stack)

    category_level = int(category_level)

    # Load the eBay cache
    cache_ebay_categories()
    ebay_categories = load_ebay_categories_cache()

    # Trim the category stack to remove deeper levels than the changed level
    category_stack = category_stack[0:category_level]

    # Get full list of category options from top level to category level
    cat_options = get_ebay_categories(ebay_categories, category_stack)

    # Trim the category options to just the level below the changed level
    # (note zero-indexing means this is really category_level + 1)
    cat_options = cat_options[category_level]

    # Format the category options ready for the Javascript select options
    if cat_options:
        for i, cat_tuple in enumerate(cat_options):
            cat_options[i] = {'value': cat_tuple[0],
                              'label': cat_tuple[1]}
    return cat_options

