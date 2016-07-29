"""Functions to deal with eBay categories and relevant category options."""

from __future__ import unicode_literals
from __future__ import print_function

import ast
import operator
import os
import pickle
from collections import OrderedDict

import frappe
from frappe import msgprint

from ebay_requests import get_categories_versions, get_categories, get_features


def _bool_process(item):
    """Replaces 'true' with True, 'false' with False, otherwise returns
    the 'item' unchanged
    """
    if item == 'true':
        return True
    if item == 'false':
        return False
    return item


def s_for(seq):
    """Returns a string of comma-separated %s markers for each
    element of the sequence; i.e. returns '%s, %s, %s, %s, %s'
    for a 5-element sequence. For SQL queries.
    """
    return ', '.join(['%s'] * len(seq))


def _load_ebay_cache_from_file(fn):
    """Return the data stored in a cache file"""
    cache_file = os.path.join(frappe.utils.get_site_path(), fn)
    with open(cache_file, 'rb') as f:
        return pickle.load(f)


def _write_ebay_cache_to_file(fn, cache_data):
    """Write the data to a cache file"""
    cache_file = os.path.join(frappe.utils.get_site_path(), fn)
    with open(cache_file, 'wb') as f:
        pickle.dump(cache_data, f, pickle.HIGHEST_PROTOCOL)


@frappe.whitelist()
def check_cache_versions():
    """Check existence and non-emptyness of tables, and check version numbers.
    Return True/False for categories and features caches.
    """
    tables_list = frappe.db.get_tables()

    # Check categories cache
    if 'eBay_categories_info' in tables_list:
        # Table exists
        categories_cache_version = frappe.db.sql(
            """SELECT CategoryVersion FROM eBay_categories_info""")
        if categories_cache_version:
            # Table is not empty
            categories_cache_version = categories_cache_version[0][0]
        else:
            categories_cache_version = None
    else:
        categories_cache_version = None

    # Check Features cache
    if 'eBay_features_info' in tables_list:
        # Table exists
        features_cache_version = frappe.db.sql(
            """SELECT CategoryVersion FROM eBay_features_info""")
        if features_cache_version:
            # Table is not empty
            features_cache_version = features_cache_version[0][0]
        else:
            features_cache_version = None
    else:
        features_cache_version = None

    # Check eBay API for current categories version
    if not (categories_cache_version is None
            and features_cache_version is None):
        categories_version, features_version = get_categories_versions()

    return (categories_version == categories_cache_version,
            features_version == features_cache_version)


@frappe.whitelist()
def ensure_updated_cache(force_categories=False, force_features=False):
    """Check if the SQL database cache of the eBay Categories and Features
    is up to date.
    If not, request new caches as needed and call create_sql_cache.
    """
    # TODO - rename this function to check_update

    categories_ok, features_ok = check_cache_versions()
    force_categories = _bool_process(force_categories)
    force_features = _bool_process(force_features)

    if force_categories or not categories_ok:
        print('WHY!!!')
        print(force_categories)
        print(not categories_ok)
        print(force_categories or not categories_ok)
        # Load new categories

        # Load using the eBay API
        # categories_data, max_level = get_categories()

        # Alternative for debugging only
        categories_data = _load_ebay_cache_from_file(
           'erpnext_ebay.categories.pkl')
        max_level = 6

        create_ebay_categories_cache(categories_data)
        frappe.db.set_value('eBay Manager Settings', None,
                            'ebay_categories_cache_maximum_level',
                            max_level)

        # Save for debugging only
        # _write_ebay_cache_to_file(
        #     'erpnext_ebay.categories.pkl', categories_data)

    if force_features or not features_ok:
        # Load new category features

        # Alternative for debugging only
        # categories_data = _load_ebay_cache_from_file(
        #    'erpnext_ebay.features.pkl')

        # Load using the eBay API
        new_features_version, features_data = get_features()

        create_ebay_features_cache(features_data)

        # Save for debugging only
        _write_ebay_cache_to_file(
            'erpnext_ebay.features.pkl', features_data)


@frappe.whitelist()
def client_get_ebay_categories(category_stack):
    """Return category options at all levels for category_stack"""

    # Frappe passes our lists as a string, so convert back to list
    # also dealing with keeping it unicode...
    if isinstance(category_stack, basestring):
        category_stack = ast.literal_eval(
            category_stack.replace('"', 'u"').replace('null', '0'))
    category_stack = [x[:-1] for x in category_stack]

    # Get full list of category options from top level to category level
    cat_options_stack = get_ebay_categories(category_stack)

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
    # also dealing with keeping it unicode...
    if isinstance(category_stack, basestring):
        category_stack = ast.literal_eval(
            category_stack.replace('"', 'u"').replace('null', '0'))
    category_stack = [x[:-1] for x in category_stack]

    category_level = int(category_level)

    # Trim the category stack to remove deeper levels than the changed level
    category_stack = category_stack[0:category_level]

    # Get full list of category options from top level to category level
    cat_options = get_ebay_categories(category_stack)

    # Trim the category options to just the level below the changed level
    # (note zero-indexing means this is really category_level + 1)
    cat_options = cat_options[category_level]

    # Format the category options ready for the Javascript select options
    if cat_options:
        for i, cat_tuple in enumerate(cat_options):
            cat_options[i] = {'value': cat_tuple[0],
                              'label': cat_tuple[1]}
    return cat_options


def get_ebay_categories(category_stack):
    """Return the category names for the category stack"""

    categories = []
    # Top-level categories
    children = frappe.db.sql("""
        SELECT CategoryID, CategoryName
        FROM eBay_categories_hierarchy WHERE CategoryParentID=0
        """, as_dict=True)
    children.sort(key=operator.itemgetter('CategoryName'))

    for i, parent_cat_id in enumerate(category_stack):

        # Add the children for our category on this level
        categories.append(
            [(x['CategoryID'],
              x['CategoryName']) for x in children])

        # If we have run out of category_stack, no more children
        if parent_cat_id == "0":
            children = []
            continue

        children = frappe.db.sql("""
            SELECT CategoryID, CategoryName
            FROM eBay_categories_hierarchy WHERE CategoryParentID=%s
            """, parent_cat_id, as_dict=True)
        children.sort(key=operator.itemgetter('CategoryName'))

    # Add the children for our category on the last level
    categories.append(
        [(x['CategoryID'],
          x['CategoryName']) for x in children])

    # Note that this will return len(category_stack) + 1 rows
    return categories


def create_ebay_categories_cache(categories_data):
    """Create SQL caches for the categories dictionaries"""

    tables_list = frappe.db.get_tables()  # Note that db.table_exists is broken

    # Drop the tables if they exist
    if 'eBay_categories_info' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_info""")
    if 'eBay_categories_hierarchy' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_hierarchy""")

    # Create the tables
    frappe.db.sql("""
        CREATE TABLE eBay_categories_info (
        Build NVARCHAR(1000),
        CategoryCount INTEGER,
        CategoryVersion NVARCHAR(1000),
        MinimumReservePrice DOUBLE PRECISION,
        ReduceReserveAllowed BOOLEAN DEFAULT false,
        ReservePriceAllowed BOOLEAN DEFAULT false,
        Timestamp NVARCHAR(100),
        Version NVARCHAR(100),
        UpdateTime NVARCHAR(100)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_categories_hierarchy (
        CategoryID NVARCHAR(10) NOT NULL,
        CategoryName NVARCHAR(30),
        CategoryLevel INTEGER,
        CategoryParentID NVARCHAR(10),
        LeafCategory BOOLEAN,
        Virtual BOOLEAN,
        Expired BOOLEAN,
        AutoPayEnabled BOOLEAN,
        B2BVATEnabled BOOLEAN,
        BestOfferEnabled BOOLEAN,
        LSD BOOLEAN,
        ORPA BOOLEAN,
        ORRA BOOLEAN,
        PRIMARY KEY (CategoryID),
        FOREIGN KEY (CategoryParentID)
            REFERENCES eBay_categories_hierarchy(CategoryID)
        )""")

    # Load the basic info into the info table
    info_od = OrderedDict()
    keys = ('Build', 'CategoryCount', 'CategoryVersion',
            'MinimumReservePrice', 'ReduceReserveAllowed',
            'ReservePriceAllowed', 'Timestamp', 'Version',
            'UpdateTime')
    for key in keys:
        if key in categories_data:
            info_od[key] = categories_data[key]
        else:
            info_od[key] = False
    frappe.db.sql("""
        INSERT INTO eBay_categories_info (""" + ", ".join(info_od.keys()) + """)
        VALUES (""" + s_for(info_od.values()) + """)
        """, info_od.values())

    # Load the categories into the database

    # A fake 'root' node
    keys = (
        'CategoryID', 'CategoryName', 'CategoryLevel', 'CategoryParentID',
        'LeafCategory', 'Virtual', 'Expired', 'AutoPayEnabled',
        'B2BVATEnabled', 'BestOfferEnabled', 'LSD', 'ORPA', 'ORRA')
    values = (0, 'ROOT', 0, None, False,
              True, False, False, False, False, False, False, False)
    hierarchy_od = OrderedDict(zip(keys, values))
    frappe.db.sql("""
        INSERT INTO eBay_categories_hierarchy
            (""" + ", ".join(hierarchy_od.keys()) + """)
        VALUES (""" + s_for(hierarchy_od.values()) + """)
        """, hierarchy_od.values())

    for cat in categories_data['TopLevel']:
        # Don't need to worry about inherited properties for categories
        for key in hierarchy_od.keys():
            if key in cat:
                hierarchy_od[key] = _bool_process(cat[key])
            else:
                hierarchy_od[key] = False
        # Point the top-level categories at the root, not themselves
        hierarchy_od['CategoryParentID'] = 0
        frappe.db.sql("""
            INSERT INTO eBay_categories_hierarchy
                (""" + ", ".join(hierarchy_od.keys()) + """)
            VALUES (""" + s_for(hierarchy_od.values()) + """)
            """, hierarchy_od.values())

        # Add the children
        cat_children = cat['Children']
        while cat_children:
            # Breadth-first walk through categories
            next_level = []
            for cat_child in cat_children:
                for key in hierarchy_od.keys():
                    if key in cat_child:
                        hierarchy_od[key] = _bool_process(cat_child[key])
                    else:
                        hierarchy_od[key] = False
                frappe.db.sql("""
                    INSERT INTO eBay_categories_hierarchy
                        (""" + ", ".join(hierarchy_od.keys()) + """)
                    VALUES (""" + s_for(hierarchy_od.values()) + """)
                    """, hierarchy_od.values())
                next_level.extend(cat_child['Children'])
            cat_children = next_level

    frappe.db.commit()


def create_ebay_features_cache(features_data):
    """Create SQL caches for the features dictionaries"""

    tables_list = frappe.db.get_tables()  # Note that db.table_exists is broken

    # Check the categories tables exist
    if not ('eBay_categories_info' in tables_list
            or 'eBay_categories_hierarchy' in tables_list):
        raise ValueError('Categories cache does not exist!')

    # Drop the tables if they exist
    if 'eBay_features_info' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_info""")
    if 'eBay_features' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features""")
    if 'eBay_features_extra' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_extra""")






    frappe.db.commit()
























