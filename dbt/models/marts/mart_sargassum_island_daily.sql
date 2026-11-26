-- One row per island per NOAA report day: what share of that island's scored coastline
-- was at each risk level. "at_or_above" shares stack: warning+ includes medium and high.
with d as (
    select d.report_date, p.island, d.risk_level
    from {{ ref('stg_sargassum_daily') }} d
    join {{ ref('stg_sargassum_points') }} p using (point_id)
)
select
    island,
    report_date,
    count(*)                                                     as points_reported,
    round(100.0 * count(*) filter (where risk_level >= 1) / count(*), 1) as pct_warning_or_higher,
    round(100.0 * count(*) filter (where risk_level >= 2) / count(*), 1) as pct_medium_or_higher,
    round(100.0 * count(*) filter (where risk_level = 3) / count(*), 1)  as pct_high,
    max(risk_level)                                              as max_risk_level,
    -- the level that covers the most coastline that day (ties go to the higher level)
    arg_max(risk_level, n_at_level * 10 + risk_level)            as typical_risk_level
from (
    select *, count(*) over (partition by island, report_date, risk_level) as n_at_level from d
)
group by 1, 2
