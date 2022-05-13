var erpnext_ebay = {
    // erpnext_ebay global JS object

    divide_rounded(values_in, total_in, dp) {
        // Divides quantities into a specified total, rounding to a specified
        // number of d.p. while ensuring that the sum of the quantities equals
        // the specified total.
        //
        // We do all maths having multiplied by 10^dp to reduce rounding issues
        // (small whole numbers are exactly representable in floating point).

        const factor = 10**dp
        // Multiply and round total first
        const total = _round(factor * total_in)
        if (total == 0) {
            frappe.throw('Total cannot be zero after rounding');
        }
        // Multiply input values by factor
        let value_sum = 0.0;
        const values = {};
        Object.entries(values_in).forEach(([k, v]) => {
            values[k] = factor * v;
            value_sum += values[k];
        });
        const mult = total / value_sum;
        const mult_obj = {};
        const rounded_obj = {};
        let rounded_sum = 0.0;
        Object.entries(values).forEach(([k, v]) => {
            mult_obj[k] = v * mult;
            rounded_obj[k] = _round(v * mult);
            rounded_sum += rounded_obj[k];
        });
        let err = rounded_sum - total;
        if (!err) {
            // Rounding was successful
            const return_obj = {};
            Object.entries(rounded_obj).forEach(([k, v]) => {
                return_obj[k] = v / factor;
            });
            return return_obj;
        }
        // Calculate rounded-off remainder
        const remainders = Object.entries(mult_obj)
            .map(([k, v]) => [k, v - rounded_obj[k]])
            .sort(([,a], [,b]) => a - b);
        if (err > 0) {
            // Values are too large
            for (let i = 0; i < err; i++) {
                [k, v] = remainders[i];
                rounded_obj[k] -= 1
            }
        } else {
            // Values are too small
            remainders.reverse();
            for (let i = 0; i < -err; i++) {
                [k, v] = remainders[i];
                rounded_obj[k] += 1
            }
        }
        const return_obj = {};
        Object.entries(rounded_obj).forEach(([k, v]) => {
            return_obj[k] = (1/factor) * v;
        });
        return return_obj;
    }

}
