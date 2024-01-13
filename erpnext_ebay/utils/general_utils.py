import operator

import frappe
from erpnext import get_default_company


def get_company_acronym():
    company = get_default_company()
    if not company:
        frappe.throw('No company!')
    return frappe.get_value('Company', company, 'abbr')


def chunker(seq, size):
    """Collect data into fixed-length chunks. From answer by nosklo in
    https://stackoverflow.com/questions/434287/
    """
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def divide_rounded(input_dict, total, dp=2):
    """Divides quantities into a specified total, rounding to a specified
    number of d.p. while ensuring that the sum of the quantities equals
    the specified total.

    We do all maths having multiplied by 10^dp to reduce rounding issues
    (whole number are exactly representable in floating point)
    """
    factor = 10**dp
    # Multiply and round total first
    total = round(factor * total)
    # Multiply input dict (not in place) by factor
    input_dict = {k: factor * v for k, v in input_dict.items()}
    if total == 0:
        raise ValueError('Total cannot be zero after rounding')
    mult = total / sum(input_dict.values())
    mult_dict = {k: v * mult for k, v in input_dict.items()}
    rounded_dict = {k: round(v) for k, v in mult_dict.items()}
    err = sum(rounded_dict.values()) - total
    if not err:
        # Rounding was successful
        return {k: (1/factor) * v for k, v in rounded_dict.items()}
    # Calculate rounded-off remainder
    remainder = [(k, mult_dict[k] - rounded_dict[k]) for k in input_dict.keys()]
    remainder.sort(key=operator.itemgetter(1))
    if err > 0:
        # Values are too large
        next_values = iter(remainder)
        for i in range(err):
            k, v = next(next_values)
            rounded_dict[k] -= 1
    else:
        # Values are too small
        next_values = reversed(remainder)
        for i in range(-err):
            k, v = next(next_values)
            rounded_dict[k] += 1
    return {k: (1/factor) * v for k, v in rounded_dict.items()}
