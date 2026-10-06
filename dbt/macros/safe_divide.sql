{#
  safe_divide(numerator, denominator)
  Division that returns NULL instead of erroring on a zero/NULL denominator.
  Used all over the marts for rates (conversion, take rate, ROAS).
#}
{% macro safe_divide(numerator, denominator) %}
    ({{ numerator }}) * 1.0 / nullif(({{ denominator }}), 0)
{% endmacro %}
