-- Consecutive unsafe results at the same beach ("gaps and islands" pattern).
-- We only look at weeks the beach was actually sampled, so a skipped week doesn't break
-- a streak, but any safe result does.
with sampled as (
    select beach_id, beach_name, island, sample_date, is_exceedance
    from {{ ref('fct_beach_samples') }}
    where station = 'main' and sample_status = 'sampled'
),
numbered as (
    select *,
        row_number() over (partition by beach_id order by sample_date)
      - row_number() over (partition by beach_id, is_exceedance order by sample_date) as grp
    from sampled
)
select
    beach_id, beach_name, island,
    min(sample_date) as streak_start,
    max(sample_date) as streak_end,
    count(*)         as consecutive_unsafe_samples
from numbered
where is_exceedance
group by beach_id, beach_name, island, grp
