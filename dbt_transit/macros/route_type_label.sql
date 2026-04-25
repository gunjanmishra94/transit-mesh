{% macro route_type_label(route_type_column) %}
    CASE {{ route_type_column }}
        WHEN 0 THEN 'Tram/Streetcar'
        WHEN 1 THEN 'Subway/Metro'
        WHEN 2 THEN 'Rail'
        WHEN 3 THEN 'Bus'
        WHEN 4 THEN 'Ferry'
        WHEN 5 THEN 'Cable Tram'
        WHEN 6 THEN 'Aerial Lift'
        WHEN 7 THEN 'Funicular'
        WHEN 11 THEN 'Trolleybus'
        WHEN 12 THEN 'Monorail'
        ELSE 'Other/Unknown'
    END
{% endmacro %}
