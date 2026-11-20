-- One row per beach: how often it has been unsafe, and what the latest result was.
with s as (
    select * from {{ ref('fct_beach_samples') }} where station = 'main'
),
latest as (
    select beach_id, sample_date as latest_date, sample_status as latest_status,
           enterococci_per_100ml as latest_enterococci,
           enterococci_qualifier as latest_qualifier, is_exceedance as latest_is_exceedance
    from s
    qualify row_number() over (partition by beach_id order by sample_date desc) = 1
)
select
    d.beach_id, d.beach_name, d.island, d.latitude, d.longitude,
    count(*) filter (where s.sample_status = 'sampled')                 as samples,
    count(*) filter (where s.is_exceedance)                             as exceedances,
    round(100.0 * count(*) filter (where s.is_exceedance)
          / nullif(count(*) filter (where s.sample_status = 'sampled'), 0), 1) as exceedance_rate_pct,
    median(s.enterococci_per_100ml) filter (where s.sample_status = 'sampled') as median_enterococci,
    max(s.enterococci_per_100ml)                                        as max_enterococci,
    max(s.sample_date) filter (where s.is_exceedance)                   as last_exceedance_date,
    l.latest_date, l.latest_status, l.latest_enterococci, l.latest_qualifier, l.latest_is_exceedance
from {{ ref('dim_beach') }} d
left join s using (beach_id)
left join latest l using (beach_id)
group by all
