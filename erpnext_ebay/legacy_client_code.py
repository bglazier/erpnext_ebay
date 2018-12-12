# -*- coding: utf-8 -*-
"""Functions to deal with eBay categories and relevant category options."""
from __future__ import unicode_literals
from __future__ import print_function

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
        AutoPayEnabled: AutoPayEnabled for current category
        BestOfferEnabled: BestOfferEnabled for current category
    """

    # Frappe passes our lists as a string, so convert back to list
    # also dealing with keeping it unicode...
    if isinstance(category_stack, six.string_types):
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
    test.category_stack.reverse()
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

    (listing_durations, condition_enabled, condition_values,
     condition_help_URL, payment_methods) = options

    # Format the condition_values options ready for the
    # Javascript select options
    if condition_values:
        condition_values = list(condition_values)
        for i, condition_item in enumerate(condition_values):
            condition_values[i] = {'value': condition_item[0],
                                   'label': condition_item[1]}

    # Format the listing duration options ready for the Javascript
    # select options
    if listing_durations:
        for listing_type, ld_list in listing_durations.items():
            ld_list.sort(key=_infinite_strings(operator.itemgetter(1)))
            new_ld_list = [{'value': x[0], 'label': x[2]} for x in ld_list]
            listing_durations[listing_type] = new_ld_list

    # For payment methods, just return a list of the valid keys
    if payment_methods:
        payment_methods = [x[0] for x in payment_methods]

    # AutoPayEnabled and BestOfferEnabled are found in the Categories, not
    # CategoryFeatures data
    auto_pay_enabled, best_offer_enabled = frappe.db.sql("""
                SELECT AutoPayEnabled, BestOfferEnabled
                from eBay_categories_hierarchy
                WHERE CategoryID=%s
                """, (category_id,), as_dict=False)[0]

    return {'category_options': cat_options_stack,
            'is_listing_category': is_listing_cat,
            'listing_durations': listing_durations,
            'condition_enabled': condition_enabled,
            'condition_values': condition_values,
            'condition_help_URL': condition_help_URL,
            'payment_methods': payment_methods,
            'AutoPayEnabled': auto_pay_enabled,
            'BestOfferEnabled': best_offer_enabled}


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
            elif (not isinstance(result, six.string_types)
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
        if isinstance(listing_types, six.string_types):
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
                """, (cat_durationSetID,), as_dict=False)

        # Collect data into (token, days, description) tuples
        return_dict[listing_type] = []
        for token_tuple in ld_sets[cat_durationSetID]:
            token = token_tuple[0]
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
