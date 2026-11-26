-- One row per beach: latest NOAA sargassum level nearby and how often it has been medium or high.
with near as (
    select beach_id, count(*) as nearby_points, min(distance_km) as nearest_point_km
    from {{ ref('int_beach_sargassum_points') }} group by 1
),
f as (select * from {{ ref('fct_beach_sargassum_daily') }}),
last_day as (select max(report_date) as d from f),
stats as (
    select f.beach_id,
           count(*)                                                as report_days,
           count(*) filter (where risk_level >= 2)                 as days_medium_or_higher,
           count(*) filter (where risk_level >= 2
                              and report_date > last_day.d - interval 30 day) as days_medium_or_higher_last_30
    from f cross join last_day group by 1
),
latest as (
    select beach_id, report_date as latest_report_date, risk_level as latest_risk_level
    from f qualify row_number() over (partition by beach_id order by report_date desc) = 1
)
select d.beach_id, near.nearby_points, near.nearest_point_km,
       latest.latest_report_date, latest.latest_risk_level,
       coalesce(stats.report_days, 0) as report_days,
       coalesce(stats.days_medium_or_higher, 0) as days_medium_or_higher,
       coalesce(stats.days_medium_or_higher_last_30, 0) as days_medium_or_higher_last_30
from {{ ref('dim_beach') }} d
left join near using (beach_id)
left join stats using (beach_id)
left join latest using (beach_id)
