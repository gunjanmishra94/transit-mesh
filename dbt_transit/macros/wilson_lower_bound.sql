{% macro wilson_lower_bound(successes_column, n_column, z=1.96) %}
    -- Wilson score interval lower bound (95% CI by default) for a binomial
    -- proportion — penalizes small samples instead of treating a route with
    -- 21 observations at 100% delayed the same as one with 5,000 at 95%.
    (
        (
            ({{ successes_column }}::DOUBLE / {{ n_column }})
            + ({{ z }} * {{ z }}) / (2 * {{ n_column }})
            - {{ z }} * SQRT(
                (({{ successes_column }}::DOUBLE / {{ n_column }}) * (1 - ({{ successes_column }}::DOUBLE / {{ n_column }})) + ({{ z }} * {{ z }}) / (4 * {{ n_column }}))
                / {{ n_column }}
            )
        )
        / (1 + ({{ z }} * {{ z }}) / {{ n_column }})
    )
{% endmacro %}
