-- Intermediate = join and de-duplicate, so marts can stay simple.
--
-- 1. Map every spelling DPNR has used to one beach_id (seed: beach_aliases.csv).
-- 2. If DPNR posted more than one PDF for the same sampling date (e.g. "-Revised"),
--    keep the most recently uploaded one - that is DPNR's final word.

with readings as (
    select * from {{ ref('stg_beach_readings') }}
),

aliases as (
    select * from {{ ref('beach_aliases') }}
),

mapped as (
    select
        r.*,
        a.beach_id,
        coalesce(nullif(a.station, ''), 'main') as station
    from readings r
    left join aliases a on a.beach_name_raw = r.beach_name_raw
),

ranked as (
    select
        *,
        row_number() over (
            partition by beach_id, station, sample_date
            order by uploaded_at desc, media_id desc
        ) as version_rank
    from mapped
)

select
    {{ dbt_utils_surrogate_key(['beach_id', 'station', 'sample_date']) }} as reading_id,
    * exclude (version_rank)
from ranked
where version_rank = 1
