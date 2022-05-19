# -*- coding: utf-8 -*-
"""Functions to deal with eBay categories and relevant category options."""

import operator
import os
import pickle
import collections

import frappe
from frappe import msgprint

from .ebay_get_requests import (
    ebay_logger, get_categories_versions, get_categories, get_features
)
from .ebay_constants import *


USE_FEATURES = False


def _infinite_strings(key=None):
    """Returns a function which returns a float: either 'inf' for a
    (base)string, or the float(value) for the argument. Intended for
    sorting numbers before strings. Accepts a 'key' argument as for
    sorting algorithms.
    """
    def _sort_func(value):
        if key is not None:
            value = key(value)
        if isinstance(value, str) or value is None:
            value = float('inf')
        else:
            value = float(value)
        return value

    return _sort_func


def _bool_process(item):
    """Replaces 'true' with True, 'false' with False, otherwise returns
    the 'item' unchanged
    """
    if item == 'true':
        return True
    if item == 'false':
        return False
    return item


def _s_for(seq):
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
def category_sync(force_override_categories=False,
                  force_override_features=False):
    """Load a new set of eBay categories.

    By default, this checks the current versions of the eBay categories cache
    and does not update it if the category version has not changed (i.e. the
    eBay categories have not changed).
    If force_override_categories is set, then the eBay categories will be
    redownloaded and new Item Group eBay entries set.
    If force_override_features is set, then the eBay features will be
    redownloaded.
    Setting force_override_features to True implies force_override_categories.
    """
    # Check permissions, as this is a whitelisted function
    if 'System Manager' not in frappe.get_roles(frappe.session.user):
        return frappe.PermissionError(
            'Only System Managers can update the eBay categories.')
    if force_override_features:
        force_override_categories = True
    categories_ok, features_ok = check_cache_versions()
    # Do we need to update the cache?
    update_categories = force_override_categories or not categories_ok
    update_features = force_override_features or not features_ok
    # Update the cache if required
    ensure_updated_cache(update_categories, update_features)
    # Update the Item Group eBay categories if required.
    if update_categories:
        # We only wipe the tables if we are forcing an override
        # otherwise we just update the existing entries.
        create_item_group_ebay(force_override_categories)


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
    categories_version, features_version = get_categories_versions()

    return (categories_version == categories_cache_version,
            features_version == features_cache_version)


def ensure_updated_cache(update_categories=False, update_features=False):
    """Check if the SQL database cache of the eBay Categories and Features
    is up to date.
    If not, request new caches as needed and call create_sql_cache.
    """

    if update_categories:
        # Load new categories

        # Load using the eBay API
        categories_data, max_level = get_categories()

        # Alternatives for debugging only
        # categories_data = _load_ebay_cache_from_file(
        #    'erpnext_ebay.categories.pkl')
        # max_level = 6

        # _write_ebay_cache_to_file(
        #     'erpnext_ebay.categories.pkl', categories_data)

        # Create SQL cache
        create_ebay_categories_cache(categories_data)
        frappe.db.set_value('eBay Manager Settings', None,
                            'ebay_categories_cache_maximum_level',
                            max_level)

    if not USE_FEATURES:
        # Don't get features data
        return

    if update_features:
        # Load new category features

        # Load using the eBay API
        new_features_version, features_data = get_features()

        # Alternatives for debugging only
        # categories_data = _load_ebay_cache_from_file(
        #    'erpnext_ebay.features.pkl')

        # _write_ebay_cache_to_file(
        #     'erpnext_ebay.features.pkl', features_data)

        # Create SQL cache
        create_ebay_features_cache(features_data)


def create_ebay_categories_cache(categories_data):
    """Create SQL caches for the categories dictionaries"""

    tables_list = frappe.db.get_tables()  # Can't use db.table_exists here

    # Drop the tables if they exist
    if 'eBay_categories_info' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_info""")
    if 'eBay_categories_hierarchy' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_hierarchy""")

    # Create the tables
    frappe.db.sql("""
        CREATE TABLE eBay_categories_info (
            Build NVARCHAR(1000),
            CategoryCount INT,
            CategoryVersion NVARCHAR(1000),
            MinimumReservePrice DOUBLE PRECISION,
            ReduceReserveAllowed BOOLEAN DEFAULT false,
            ReservePriceAllowed BOOLEAN DEFAULT false,
            Timestamp NVARCHAR(100),
            UpdateTime NVARCHAR(100),
            Version NVARCHAR(100)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_categories_hierarchy (
            CategoryID NVARCHAR(19) NOT NULL,
            CategoryName NVARCHAR(60),
            CategoryLevel INT,
            CategoryParentID NVARCHAR(19),
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
    info_od = collections.OrderedDict()
    keys = ('Build', 'CategoryCount', 'CategoryVersion',
            'MinimumReservePrice', 'ReduceReserveAllowed',
            'ReservePriceAllowed', 'Timestamp', 'UpdateTime',
            'Version')
    for key in keys:
        if key in categories_data:
            info_od[key] = _bool_process(categories_data[key])
        else:
            info_od[key] = False
    frappe.db.sql("""
        INSERT INTO eBay_categories_info
            (""" + ", ".join(list(info_od.keys())) + """)
            VALUES (""" + _s_for(info_od.values()) + """)
        """, list(info_od.values()))  # nosec
    # nosec: keys are hardcoded, and values are passed by parameterisation.

    # Load the categories into the database

    # A fake 'root' node
    keys = (
        'CategoryID', 'CategoryName', 'CategoryLevel', 'CategoryParentID',
        'LeafCategory', 'Virtual', 'Expired', 'AutoPayEnabled',
        'B2BVATEnabled', 'BestOfferEnabled', 'LSD', 'ORPA', 'ORRA')
    values = (0, 'ROOT', 0, None, False,
              True, False, False, False, False, False, False, False)
    hierarchy_od = collections.OrderedDict(zip(keys, values))
    frappe.db.sql("""
        INSERT INTO eBay_categories_hierarchy
            (""" + ", ".join(hierarchy_od.keys()) + """)
            VALUES (""" + _s_for(hierarchy_od.values()) + """)
        """, list(hierarchy_od.values()))  # nosec
    # nosec: keys are hardcoded, and values are passed by parameterisation.

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
                VALUES (""" + _s_for(hierarchy_od.values()) + """)
            """, list(hierarchy_od.values()))

        # Add the children
        cat_children = cat['Children']
        while cat_children:
            # Breadth-first walk through categories
            next_level = []
            for cat_child in cat_children:
                for key in list(hierarchy_od.keys()):
                    if key in cat_child:
                        hierarchy_od[key] = _bool_process(cat_child[key])
                    else:
                        hierarchy_od[key] = False
                frappe.db.sql("""
                INSERT INTO eBay_categories_hierarchy
                    (""" + ", ".join(hierarchy_od.keys()) + """)
                    VALUES (""" + _s_for(hierarchy_od.values()) + """)
                """, list(hierarchy_od.values()))  # nosec
                # nosec: keys are hardcoded, and values
                # are passed by parameterisation.
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
    if 'eBay_features_PaymentMethodConnections' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_PaymentMethodConnections""")
    if 'eBay_features_extra' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_extra""")
    if 'eBay_features' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features""")
    if 'eBay_features_ListingDurations' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_ListingDurations""")
    if 'eBay_features_FeatureDefinitions' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_FeatureDefinitions""")
    if 'eBay_features_ConditionValues' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_ConditionValues""")
    if 'eBay_features_PaymentMethods' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_PaymentMethods""")
    if 'eBay_features_ListingDurationTokens' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_features_ListingDurationTokens""")

# Create the tables

    # Lookup tables for hard-coded eBay tokens
    frappe.db.sql("""
        CREATE TABLE eBay_features_ListingDurationTokens (
            ListingDurationToken NVARCHAR(20),
            Days INT,
            Description NVARCHAR(1000),
            PRIMARY KEY (ListingDurationToken)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_PaymentMethods (
            PaymentMethod NVARCHAR(100),
            Description NVARCHAR(1000),
            PRIMARY KEY (PaymentMethod)
        )""")

    # Tables for the features data
    frappe.db.sql("""
        CREATE TABLE eBay_features_info (
            Build NVARCHAR(1000),
            CategoryVersion NVARCHAR(1000),
            ListingDurationVersion INT,
            Timestamp NVARCHAR(100),
            UpdateTime NVARCHAR(100),
            Version NVARCHAR(100)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_ConditionValues (
            CategoryID NVARCHAR(10) NOT NULL,
            ConditionID INT NOT NULL,
            DisplayName NVARCHAR(1000),
            FOREIGN KEY (CategoryID)
                REFERENCES eBay_categories_hierarchy (CategoryID)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_FeatureDefinitions (
            FeatureDefinition NVARCHAR(""" + EBAY_ATTR_LEN_STR + """),
            Extra BOOLEAN NOT NULL,
            PRIMARY KEY (FeatureDefinition)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_ListingDurations (
            durationSetID INT NOT NULL,
            ListingDurationToken NVARCHAR(20),
            FOREIGN KEY (ListingDurationToken)
                REFERENCES eBay_features_ListingDurationTokens (
                    ListingDurationToken)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_PaymentMethodConnections (
            CategoryID NVARCHAR(10) NOT NULL,
            PaymentMethod NVARCHAR(100) NOT NULL,
            FOREIGN KEY (CategoryID)
                REFERENCES eBay_categories_hierarchy (CategoryID),
            FOREIGN KEY (PaymentMethod)
                REFERENCES eBay_features_PaymentMethods (PaymentMethod)
        )""")

    # NOTE - changes here should be matched by changes to the
    # FEATURES_BASE_COLUMNS constant
    frappe.db.sql("""
        CREATE TABLE eBay_features (
            CategoryID NVARCHAR(10) NOT NULL,
            ListingDurationAdType INT,
            ListingDurationAuction INT,
            ListingDurationChinese INT,
            ListingDurationDutch INT,
            ListingDurationLive INT,
            ListingDurationFixedPriceItem INT,
            ListingDurationLeadGeneration INT,
            ListingDurationPersonalOffer INT,
            ListingDurationStoresFixedPrice INT,
            CompatibleVehicleType NVARCHAR(100),
            ExpressEnabled BOOLEAN,
            GlobalShippingEnabled BOOLEAN,
            MaxFlatShippingCost DOUBLE PRECISION,
            MaxFlatShippingCostCurrency NVARCHAR(10),
            ConditionEnabled NVARCHAR(100),
            ConditionHelpURL NVARCHAR(1000),
            FOREIGN KEY (CategoryID)
                REFERENCES eBay_categories_hierarchy (CategoryID)
        )""")

    frappe.db.sql("""
        CREATE TABLE eBay_features_extra (
            CategoryID NVARCHAR(10) NOT NULL,
            Attribute NVARCHAR(""" + EBAY_ATTR_LEN_STR + """) NOT NULL,
            Value NVARCHAR(""" + EBAY_VALUE_LEN_STR + """),
            FOREIGN KEY (CategoryID)
                REFERENCES eBay_categories_hierarchy (CategoryID),
            UNIQUE cat_attr (CategoryID, Attribute)
        )""")

    # Set up the tables with hard-coded eBay constants

    # Set up the eBay_features_ListingDurationTokens table
    for values in LISTING_DURATION_TOKENS:
        frappe.db.sql("""
            INSERT INTO eBay_features_ListingDurationTokens
                (ListingDurationToken, Days, Description)
                VALUES (%s, %s, %s)
            """, values)

    for key, value in PAYMENT_METHODS.items():
        frappe.db.sql("""
            INSERT INTO eBay_features_PaymentMethods
                (PaymentMethod, Description)
                VALUES (%s, %s)
            """, (key, value))

    frappe.db.commit()

    # Set up the tables for the features data

    # Load the basic info into the info table
    info_od = collections.OrderedDict()
    keys = ('Build', 'CategoryVersion', 'ListingDurationVersion',
            'Timestamp', 'UpdateTime', 'Version')
    for key in keys:
        if key in features_data:
            info_od[key] = features_data[key]
        else:
            info_od[key] = False
    frappe.db.sql("""
        INSERT INTO eBay_features_info (""" + ", ".join(info_od.keys()) + """)
            VALUES (""" + _s_for(info_od.values()) + """)
        """, list(info_od.values()))

    # Set up the eBay_features_FeatureDefinitions table
    for fd in features_data['FeatureDefinitions']:
        if fd in FEATURES_NOT_SUPPORTED:
            continue
        extra = fd not in FEATURES_NOT_EXTRA
        frappe.db.sql("""
            INSERT INTO eBay_features_FeatureDefinitions
                (FeatureDefinition, Extra)
                VALUES (%s, %s)
            """, (fd, extra))

    # Set up the eBay_features_ListingDurations table
    for ld_key, tokens in features_data['ListingDurations'].items():
        if isinstance(tokens, str):
            tokens = (tokens,)
        for token in tokens:
            frappe.db.sql("""
                INSERT INTO eBay_features_ListingDurations
                    (durationSetID, ListingDurationToken)
                    VALUES (%s, %s)
                """, (ld_key, token))

    # Loop over categories, setting up the remaining tables
    cat_keys = FEATURES_BASE_COLUMNS

    # First set up the ROOT (CategoryID = 0) element with the SiteDefaults
    root_cat = features_data['SiteDefaults'].copy()
    root_cat['CategoryID'] = 0
    features_data['Category'].insert(0, root_cat)

    local_unsupported = []
    for cat in features_data['Category']:
        # OrderedDict to store values for main table
        cat_od = collections.OrderedDict()
        for key in cat_keys:
            cat_od[key] = None
        cat_id = cat['CategoryID']
        # Loop over attributes and values
        for key, value in cat.items():
            if key == 'ListingDuration':
                if not isinstance(value, collections.Sequence):
                    value = (value,)
                for ld_dict in value:
                    ld_key_str = 'ListingDuration' + ld_dict['_type']
                    cat_od[ld_key_str] = ld_dict['value']
            elif key == 'PaymentMethod':
                if isinstance(value, str):
                    value = (value,)
                for payment_method in value:
                    frappe.db.sql("""
                        INSERT INTO eBay_features_PaymentMethodConnections (
                            CategoryID, PaymentMethod )
                            VALUES (%s, %s)
                        """, (cat_id, payment_method))
            elif key == 'ConditionValues':
                if not isinstance(value, collections.Sequence):
                    value = (value,)
                for cv_dict in value:
                    frappe.db.sql("""
                        INSERT INTO eBay_features_ConditionValues (
                            CategoryID, ConditionID, DisplayName )
                            VALUES (%s, %s, %s)
                        """, (cat_id, cv_dict['ID'], cv_dict['DisplayName']))
            elif key == 'MaxFlatShippingCost':
                cat_od['MaxFlatShippingCostCurrency'] = value['_currencyID']
                cat_od['MaxFlatShippingCost'] = value['value']
            elif key in cat_keys:
                # This is one of the expected keys
                cat_od[key] = value
            else:
                # This is an 'extra' key
                if key in FEATURES_NOT_SUPPORTED:
                    continue
                if key in local_unsupported:
                    continue
                if (
                        not isinstance(value, str)
                        or len(key) > EBAY_ATTR_LEN
                        or len(value) > EBAY_VALUE_LEN):
                    ebay_logger().debug(
                        f'Unsupported eBay attribute/value: {key} : {value}')
                    local_unsupported.append(key)
                    raise ValueError('Fancy unsupported data type!')
                frappe.db.sql("""
                    INSERT INTO eBay_features_extra (
                        CategoryID, Attribute, Value )
                        VALUES (%s, %s, %s)
                """, (cat_id, key, value))

        # Insert the completed row for this category
        frappe.db.sql("""
            INSERT INTO eBay_features (""" + ", ".join(list(cat_od.keys())) + """)
                VALUES (""" + _s_for(cat_od.values()) + """)
            """, list(cat_od.values()))

    frappe.db.commit()


def get_category_stack(category_id):
    """Given a CategoryID, return the category_stack.

    The category stack goes from deepest -> top category.
    """
    category_stack = []
    while category_id != "0":
        category_stack.append(category_id)
        category_query = frappe.db.sql("""
            SELECT CategoryParentID
                FROM eBay_categories_hierarchy
                WHERE CategoryID=%s
            """, (category_id,), as_dict=True)
        if len(category_query) == 0:
            raise ValueError('eBay category ID {} not found'.format(
                category_id))
        if len(category_query) > 1:
            raise ValueError('eBay category with non-unique CategoryID!')
        category_id = category_query[0]['CategoryParentID']
    return category_stack


def get_category_name_stack(category_id):
    """Given a CategoryID, return the category_stack

    The category stack goes from deepest -> top category.
    """
    category_name_stack = []
    while category_id != "0":
        category_query = frappe.db.sql("""
            SELECT CategoryParentID, CategoryName
                FROM eBay_categories_hierarchy
                WHERE CategoryID=%s
            """, (category_id,), as_dict=True)
        if len(category_query) == 0:
            raise ValueError('eBay category ID {} not found'.format(
                category_id))
        if len(category_query) > 1:
            raise ValueError('eBay category with non-unique CategoryID!')
        category_id = category_query[0]['CategoryParentID']
        category_name_stack.append(category_query[0]['CategoryName'])
    return category_name_stack


def create_item_group_ebay(force_delete=False):
    """Creates Item Group Ebay documents from the eBay categories cache."""

    # DANGER - items that link to these Item Group eBay documents will be
    # left hanging if the categories disappear.

    if not force_delete:
        # If we are not force-deleting, check for current Item Group eBay
        # entries. We will prefer to update these rather than replace them.
        ige_list = frappe.db.sql("""
            SELECT ebay_category_id, ebay_category_name, ebay_category,
                ebay_expired, ebay_virtual, name
                FROM `tabItem Group eBay`;
            """, as_dict=True)

        ige_dict = {x['ebay_category_id']: x for x in ige_list}

        if len(ige_list) != len(ige_dict):
            # There are multiple categories with the same ebay_category_id
            force_delete = True
        del ige_list

    if force_delete:
        # This is slower than TRUNCATE TABLE but doesn't lead to an
        # implicit commit, which often causes an error.
        frappe.db.sql("""DELETE FROM `tabItem Group eBay`;""")
        frappe.db.commit()
        ige_dict = {}

    cats = frappe.db.sql("""
        SELECT CategoryID, CategoryParentID, CategoryName,
            LeafCategory, Expired, Virtual
            FROM eBay_categories_hierarchy;
        """, as_dict=True)

    parent_dict = {}
    names_dict = {}
    for cat in cats:
        parent_dict[cat['CategoryID']] = cat['CategoryParentID']
        names_dict[cat['CategoryID']] = cat['CategoryName']

    # Filter out non-leaf categories
    cats = [x for x in cats if x['LeafCategory']]
    cat_ids = {x['CategoryID'] for x in cats}

    # Delete any categories that exist in the DB but are not current
    if not force_delete:
        ige_cat_ids = set(ige_dict.keys())
        deleted_ids = ige_cat_ids - cat_ids
        for deleted_id in deleted_ids:
            frappe.delete_doc('Item Group eBay', ige_dict[deleted_id].name,
                            force=True)

    for i, cat in enumerate(cats):
        #print(' {:05} / {}'.format(i + 1, len(cats)))

        cat_id = cat['CategoryID']
        cat_name = f"""{cat['CategoryName']} {cat_id}"""
        cat_name_stack = [cat['CategoryName']]
        cat_search_id = parent_dict[cat_id]
        while cat_search_id != "0":
            cat_name_stack.append(names_dict[cat_search_id])
            cat_search_id = parent_dict[cat_search_id]

        cat_name_stack.reverse()
        cat_label = ' | '.join(cat_name_stack)  # or ' => '

        # Test if this category already exists
        if not force_delete and cat['CategoryID'] in ige_dict:
            # Matching category ID exists. If it matches perfectly,
            # we do nothing.
            ige = ige_dict[cat_id]
            if not (ige['ebay_category_name'] == cat_name
                    and ige['ebay_category'] == cat_label
                    and ige['ebay_expired'] == cat['Expired']
                    and ige['ebay_virtual'] == cat['Virtual']):
                # Update the not-quite matching category
                item_group_ebay_doc = frappe.get_doc(
                    'Item Group eBay', ige['name'])
                item_group_ebay_doc.ebay_category_name = cat_name
                item_group_ebay_doc.ebay_category = cat_label
                item_group_ebay_doc.ebay_expired = cat['Expired']
                item_group_ebay_doc.ebay_expired = cat['Virtual']
                item_group_ebay_doc.save()
            del ige_dict[cat_id]

        else:
            # No matching category found - create a new category
            item_group_ebay_doc = frappe.get_doc({
                "doctype": "Item Group eBay",
                "ebay_category_id": cat['CategoryID'],
                "ebay_category_name": cat_name,
                "ebay_category": cat_label,
                "ebay_expired": cat['Expired'],
                "ebay_virtual": cat['Virtual']})

            item_group_ebay_doc.insert(ignore_permissions=True)

    frappe.db.commit()
