-- Every SIR file the pipeline tried to fetch. status = saved or missing (NOAA had no file).
select
    strptime(report_date, '%Y%m%d')::date as report_date,  -- the log keeps NOAA's YYYYMMDD style
    url,
    sha256,
    cast(bytes as bigint)           as bytes,
    cast(usvi_points as integer)    as usvi_points,
    status,
    cast(fetched_at_utc as timestamp) as fetched_at_utc
from {{ source('raw', 'sargassum_downloads') }}
