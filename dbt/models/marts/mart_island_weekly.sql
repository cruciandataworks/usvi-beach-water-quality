-- One row per island per sampling date: how many beaches were tested and how many failed.
select
    sample_date,
    island,
    count(*) filter (where sample_status = 'sampled')   as beaches_sampled,
    count(*) filter (where is_exceedance)               as beaches_unsafe,
    count(*) filter (where sample_status = 'not_sampled') as beaches_not_sampled,
    round(100.0 * count(*) filter (where is_exceedance)
          / nullif(count(*) filter (where sample_status = 'sampled'), 0), 1) as pct_unsafe
from {{ ref('fct_beach_samples') }}
where station = 'main'
group by all
