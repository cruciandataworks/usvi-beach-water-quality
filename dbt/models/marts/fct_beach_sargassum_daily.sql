-- One row per beach per NOAA report day: the worst (highest) risk level among the
-- coastline points near that beach. If NOAA had no usable data for any of them that
-- day, there is no row - we never fill gaps with a guess.
select
    n.beach_id,
    d.report_date,
    max(d.risk_level)   as risk_level,
    count(*)            as points_reported
from {{ ref('int_beach_sargassum_points') }} n
join {{ ref('stg_sargassum_daily') }} d using (point_id)
group by 1, 2
