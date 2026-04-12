{{ config(materialized='view') }}

SELECT
    agency_id,
    agency_name,
    agency_url,
    agency_timezone,
    agency_lang
FROM {{ source('transit', 'raw_gtfs_agency') }}
