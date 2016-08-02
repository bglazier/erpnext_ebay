"""Functions to deal with eBay categories and relevant category options."""

from __future__ import unicode_literals
from __future__ import print_function

import ast
import operator
import os
import pickle
import collections

import frappe
from frappe import msgprint

from ebay_requests import get_categories_versions, get_categories, get_features
from ebay_constants import *


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

    categories_ok, features_ok = check_cache_versions()
    force_categories = _bool_process(force_categories)
    force_features = _bool_process(force_features)

    if force_categories or not categories_ok:
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

    if force_features or not features_ok:
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


@frappe.whitelist()
def client_get_new_categories_data(category_level, category_stack):
    """Return all relevant information given new category information.

    If category_level is zero, return category options for all categories.
    If category_level is non-zero, return category options only for that level.

    Returns a dictionary:
        category_options: [list of category option strings]
        is_listing_category: is a listing category currently selected?
        listing_durations: [list of listing_duration tuples]
        condition_values: [list of ConditionID tuples]
        ConditionHelpURL: ConditionHelpURL for current category or None
    """

    # Frappe passes our lists as a string, so convert back to list
    # also dealing with keeping it unicode...
    if isinstance(category_stack, basestring):
        category_stack = ast.literal_eval(
            category_stack.replace('"', 'u"').replace('null', '0'))
    category_stack = [x[:-1] for x in category_stack]

    category_level = int(category_level)

    if category_level == 0:
        # Find last non-zero/True category
        category_id = 0
        for i, cat_id in enumerate(category_stack):
            if (not cat_id) or (cat_id == '0'):
                break
            category_id = cat_id
            category_level = i + 1
    else:
        # Trim the category stack to remove deeper levels
        # than the changed level
        category_stack = category_stack[0:category_level]
        category_id = category_stack[category_level-1]

    # Validate the category stack
    test_category_stack = get_category_stack(category_id)
    if test_category_stack != category_stack[0:category_level]:
        raise ValueError('Invalid category stack passed!')

    # Get full list of category options from top level to category level
    cat_options_stack = get_ebay_categories(category_stack)

    # Format the category options ready for the Javascript select options
    for cat_options in cat_options_stack:
        if cat_options:
            for i, cat_tuple in enumerate(cat_options):
                cat_options[i] = {'value': cat_tuple[0],
                                  'label': cat_tuple[1]}

    # Is the currently selected category a listing category?
    is_listing_cat = is_listing_category(category_id)

    # Search functions and matching arguments:
    # 1) Listing durations
    # 2) ConditionEnabled
    # 3) Condition Values
    # 4) ConditionHelpURL
    # 5) Payment methods
    search_functions = (get_listing_durations,
                        get_feature_property_basic,
                        get_condition_values,
                        get_feature_property_basic,
                        get_payment_methods)
    search_args = ({'listing_types': LISTING_TYPES_SUPPORTED},
                   {'property_name': 'ConditionEnabled'},
                   None,
                   {'property_name': 'ConditionHelpURL'},
                   None)

    options = get_overridden_options(category_stack[0:category_level],
                                     search_functions, search_args)
    print(options)

    return {'category_options': cat_options_stack,
            'is_listing_category': is_listing_cat,
            'listing_durations': options[0],
            'condition_enabled': options[1],
            'condition_values': options[2],
            'condition_help_URL': options[3],
            'payment_methods': options[4]}


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
            CategoryID NVARCHAR(10) NOT NULL,
            CategoryName NVARCHAR(30),
            CategoryLevel INT,
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
    info_od = collections.OrderedDict()
    keys = ('Build', 'CategoryCount', 'CategoryVersion',
            'MinimumReservePrice', 'ReduceReserveAllowed',
            'ReservePriceAllowed', 'Timestamp', 'UpdateTime',
            'Version')
    for key in keys:
        if key in categories_data:
            info_od[key] = categories_data[key]
        else:
            info_od[key] = False
    frappe.db.sql("""
        INSERT INTO eBay_categories_info (""" + ", ".join(info_od.keys()) + """)
            VALUES (""" + _s_for(info_od.values()) + """)
        """, info_od.values())

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
                VALUES (""" + _s_for(hierarchy_od.values()) + """)
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
                        VALUES (""" + _s_for(hierarchy_od.values()) + """)
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
        """, info_od.values())

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
        if isinstance(tokens, basestring):
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
                if isinstance(value, basestring):
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
                       not isinstance(value, basestring)
                        or len(key) > EBAY_ATTR_LEN
                        or len(value) > EBAY_VALUE_LEN):
                    print('Unsupported eBay attribute/value: {} : {}'.format(
                        key, value))
                    frappe.log(
                        'Unsupported eBay attribute/value: {} : {}'.format(
                            key, value))
                    local_unsupported.append(key)
                    raise ValueError('Fancy unsupported data type!')
                frappe.db.sql("""
                    INSERT INTO eBay_features_extra (
                        CategoryID, Attribute, Value )
                        VALUES (%s, %s, %s)
                """, (cat_id, key, value))

        # Insert the completed row for this category
        frappe.db.sql("""
            INSERT INTO eBay_features (""" + ", ".join(cat_od.keys()) + """)
                VALUES (""" + _s_for(cat_od.values()) + """)
            """, cat_od.values())

    frappe.db.commit()


def get_category_stack(category_id):
    """Given a CategoryID, return the category_stack"""
    category_stack = []
    while category_id != "0":
        category_stack.append(category_id)
        category_id = frappe.db.sql("""
            SELECT CategoryParentID
                FROM eBay_categories_hierarchy
                WHERE CategoryID=%s
            """, (category_id,))
        category_id = category_id[0][0]
    category_stack.reverse()
    return category_stack


def scalar_search_function(f):
    """Function decorator that marks functions for get_overridden_options
    indicating that the result should be treated as a scalar.
    This decorator is optional.
    """
    f._search_multiple_elements = False
    return f


def multiple_search_function(f):
    """Function decorator that marks functions for get_overridden_options
    indicating that the result should be checked treating each element
    separately."""
    f._search_multiple_elements = True
    return f


def get_overridden_options(category_stack, search_functions, sf_args_seq=None):
    """Using a search_function with search_args, find the options for a
    category. The search_function is called repeatedly, starting at the deepest
    category and moving towards the root category, to find all overridden
    arguments.

    category_stack - a sequence of CategoryID values
    search_functions - a sequence of search functions
    sf_args - a sequence of mapping types (e.g. a dict) containing
              arguments for the search_functions

    The search function should accept the category id as the first argument.
    Any sf_args will be passed to the search function. The value None indicates
    that there is no override for this category.

    If the search function
    has been decorated with multiple_search_function, then it can return
    either:
        a) A sequence type (e.g. a list) - each entry is a property
        b) A mapping type (e.g. a dictionary) - each key/value is a property
    The format of the sequence or mapping types (length or keys) should be
    consistent, and should be mutable. Each element will be considered
    separately when checking for overrides.

    If it has been decorated with single_search_function or has not been
    decorated, then it can return any result. This will be treated as a
    single value.

    Returns a list, with one entry for each search function, of results in
    whatever format was returned by each search_function.
    """

    # Deal with a single search_function and search_args dict
    if not isinstance(search_functions, collections.Sequence):
        search_functions = (search_functions,)
        sf_args_seq = (sf_args_seq,)

    n_search = len(search_functions)
    search_done = [False for x in search_functions]
    search_multiple_elements = [hasattr(f, '_search_multiple_elements')
                                and f._search_multiple_elements
                                for f in search_functions]
    results = [None for x in search_functions]
    if sf_args_seq is None:
        sf_args_seq = [[] for x in search_functions]

    # We need to add the 'root' node to get the SiteDefaults
    category_stack.insert(0, "0")

    for category_id in reversed(category_stack):
        for i_search, search_function in enumerate(search_functions):
            if search_done[i_search]:
                # We have completed this search
                continue
            search_args = sf_args_seq[i_search]
            if search_args is None:
                search_args = {}
            result = search_function(category_id, **search_args)
            if result is None:
                continue
            # We have some results
            if not search_multiple_elements[i_search]:
                # Scalar results (the default)
                results[i_search] = result
                search_done[i_search] = True
            elif isinstance(result, collections.Mapping):
                # Multiple results; treat each element separately
                # We have a dict-type object, loop over keys
                if results[i_search] is None:
                    results[i_search] = result
                else:
                    for key in result:
                        if (result[key] is None
                                or results[i_search][key] is None):
                            results[i_search][key] = result[key]
                if None not in results[i_search].values():
                    search_done[i_search] = True
            elif (not isinstance(result, basestring)
                    and isinstance(result, collections.Sequence)):
                # Multiple results; treat each element separately
                # We have a list-type value, loop over values
                if results[i_search] is None:
                    results[i_search] = result
                else:
                    for i, result_item in enumerate(result):
                        if result_item is None or results[i_search][i] is None:
                            results[i_search][i] = result_item
                if None not in results[i_search]:
                    search_done[i_search] = True
            else:
                raise ValueError('If decorated as a multiple_search_function, '
                                 + 'must return a sequence or mapping type!')

    return results


@scalar_search_function
def get_feature_property_basic(category_id, property_name):
    """Given a CategoryID, return the selected 'property_name' overrides
    for that category, if they exist. This function must be called repeatedly
    over parent categories to return the actual options for a category. If
    there is no override for each listing_type, return None for that category.
    This function only handles 'basic' properties in the eBay_features table,
    not 'extra' properties in the 'eBay_features_extra' EAV table.

    category_id   - valid CategoryID (can be zero for the SiteDefaults)
    property_name - valid database property

    Returns: The requested property
    """

    # SQL string interpolation ahead, so need to verify valid property name
    if property_name not in FEATURES_BASE_COLUMNS:
        raise ValueError('Trying to look up illegal column name!')

    rows = frappe.db.sql("""
        SELECT """ + property_name + """ FROM eBay_features
            WHERE CategoryID=%s
        """, (category_id))

    if not rows:
        rows = None
    else:
        rows = rows[0][0]
    return rows


@scalar_search_function
def get_condition_values(category_id):
    """Given a CategoryID, return the selected ConditionValue overrides
    for that category, if they exist. This function must be called repeatedly
    over parent categories to return the actual options for a category. If
    there is no override for each listing_type, return None for that category.

    category_id - valid CategoryID (can be zero for the SiteDefaults)

    Returns: list of lists. Each list item is a two-element list:
        [valid ConditionID, its description]
    """
    rows = frappe.db.sql("""
        SELECT ConditionID, DisplayName FROM eBay_features_ConditionValues
            WHERE CategoryID=%s
        """, (category_id))

    if not rows:
        rows = None
    return rows


@scalar_search_function
def get_payment_methods(category_id):
    """Given a CategoryID, return the selected PaymentMethod overrides
    for that category, if they exist. This function must be called repeatedly
    over parent categories to return the actual options for a category. If
    there is no override for each listing_type, return None for that category.

    category_id - valid CategoryID (can be zero for the SiteDefaults)

    Returns: list of lists. Each list item is a two-element list:
        [valid PaymentMethod, its description].
    """
    rows = frappe.db.sql("""
        SELECT
            eBay_features_PaymentMethodConnections.PaymentMethod, Description
            FROM eBay_features_PaymentMethodConnections
            LEFT OUTER JOIN eBay_features_PaymentMethods
            ON eBay_features_PaymentMethodConnections.PaymentMethod
                = eBay_features_PaymentMethods.PaymentMethod
            WHERE CategoryID=%s;
        """, (category_id))

    if not rows:
        rows = None
    return rows


@multiple_search_function
def get_listing_durations(category_id, listing_types=None):
    """Given a CategoryID, return the selected listing durations overrides
    for that category, if they exist. This function must be called repeatedly
    over parent categories to return the actual options for a category. If
    there is no override for each listing_type, return None for that category.

    category_id   - valid CategoryID (can be zero for the SiteDefaults)
    listing_types - either a valid listing type, or a sequence of valid
                    listing types, or None for all supported listing types.

    Returns: dictionary (or None). Keys are listing types; values are either a
        list of the acceptable listing durations or None if there is no
        override for this category. Each Listing duration is a tuple of the
        ListingDurationToken (string), days (int) and Description (string).
        If the category does not appear in the features table at all, None
        will be returned instead.
    """

    if listing_types is None:
        # Return options for all supported listing types
        listing_types = LISTING_TYPES_SUPPORTED
    else:
        # User input, so need to do some validation (later SQL query)
        if isinstance(listing_types, basestring):
            listing_types = (listing_types,)
        for listing_type in listing_types:
            if listing_type not in LISTING_TYPES:
                raise ValueError('Unknown listing type!')

    return_dict = {}

    listing_duration_type = {x: 'ListingDuration' + x for x in listing_types}
    listing_column_list = ', '.join(listing_duration_type.values())
    # NOTE interpolation in the SQL query, so ensure listing types
    # are validated
    cat_durationSetIDs = frappe.db.sql("""
        SELECT """ + listing_column_list + """
            FROM eBay_features
            WHERE CategoryID=%s
        """, (category_id,), as_dict=True)

    if cat_durationSetIDs:
        cat_durationSetIDs = cat_durationSetIDs[0]
    else:
        # This category does not appear in the features table, and so
        # has no overrides
        return None

    if cat_durationSetIDs.values().count(None) == len(listing_column_list):
        # There are no ListingDuration overrides for this category
        return cat_durationSetIDs

    ld_sets = {}

    for listing_type in listing_types:
        # Loop over listing_type, checking the returned durationSetID for
        # each listing_type against the database to return the list of
        # ListingDuration tokens. ld_sets is a cached dictionary of
        # durationSetID : list(ListingDuration tokens).

        ld_col_name = listing_duration_type[listing_type]
        cat_durationSetID = cat_durationSetIDs[ld_col_name]

        if cat_durationSetID is None:
            # There is no override for this listing_type on this category
            return_dict[listing_type] = None

        # Ensure we have the ListingDurationToken list cached
        # for this durationSetID
        if cat_durationSetID not in ld_sets:
            # Load the relevant ListingDuration from the database
            ld_sets[cat_durationSetID] = frappe.db.sql("""
                SELECT ListingDurationToken from eBay_features_ListingDurations
                WHERE durationSetID=%s
                """, (cat_durationSetID,), as_dict=False)[0]

        # Collect data into (token, days, description) tuples
        return_dict[listing_type] = []
        for token in ld_sets[cat_durationSetID]:
            days = LISTING_DURATION_TOKEN_DICT[token][0]
            description = LISTING_DURATION_TOKEN_DICT[token][1]
            return_dict[listing_type].append(
                (token, days, description))

    return return_dict


def is_listing_category(category_id):
    """Check that the category with CategoryID is a leaf category which is
    neither expired nor virtual."""

    # 'Root' category is not real, and is never a listing category
    if (not category_id) or (category_id == "0"):
        return False

    leaf, virtual, expired = frappe.db.sql("""
        SELECT LeafCategory, Virtual, Expired FROM eBay_categories_hierarchy
            WHERE CategoryID=%s
        """, (category_id,))[0]

    return leaf and not (virtual or expired)













