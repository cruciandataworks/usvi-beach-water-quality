-- Does a sargassum warning line up with unsafe bacteria results?
-- For every DPNR sample taken since NOAA's archive starts, look back over the
-- {{ var('sargassum_lookback_days') }} days up to and including the sampling day and take the
-- highest sargassum level near that beach. Then the export compares unsafe rates by level.
-- This is a comparison, not proof of cause: rain runoff, sewage and wind also matter.
with s as (
    select beach_id, beach_name, island, sample_date, is_exceedance, enterococci_per_100ml
    from {{ ref('fct_beach_samples') }}
    where station = 'main' and sample_status = 'sampled'
      and sample_date >= (select min(report_date) from {{ ref('stg_sargassum_daily') }})
),
lookback as (
    select s.beach_id, s.sample_date,
           max(f.risk_level)            as max_risk_level_lookback,
           count(distinct f.report_date) as report_days_in_lookback
    from s
    join {{ ref('fct_beach_sargassum_daily') }} f
      on f.beach_id = s.beach_id
     and f.report_date between s.sample_date - interval {{ var('sargassum_lookback_days') - 1 }} day
                           and s.sample_date
    group by 1, 2
)
select s.*, l.max_risk_level_lookback, l.report_days_in_lookback
from s
left join lookback l using (beach_id, sample_date)
