-- One row per report day and coastline point.
-- NOAA's legend: 0 low (blue), 1 warning (yellow), 2 medium (orange), 3 high (red).
-- Points NOAA paints black ("insufficient data") are simply absent from the file.
select
    cast(report_date as date)   as report_date,
    cast(point_id as integer)   as point_id,
    cast(risk as integer)       as risk_level,
    case cast(risk as integer)
        when 0 then 'low' when 1 then 'warning' when 2 then 'medium' when 3 then 'high'
    end                         as risk_label
from {{ source('raw', 'sargassum_daily') }}
