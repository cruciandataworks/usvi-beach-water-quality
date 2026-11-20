-- One row per beach: name, island, map location, and when DPNR has data for it.
with beaches as (select * from {{ ref('beaches') }}),
loc as (select * from {{ ref('beach_locations') }}),
seen as (
    select beach_id,
           min(sample_date) filter (where sample_status = 'sampled') as first_sampled,
           max(sample_date) filter (where sample_status = 'sampled') as last_sampled
    from {{ ref('int_readings_resolved') }}
    group by 1
)
select
    b.beach_id,
    b.beach_name,
    b.island,
    l.latitude,
    l.longitude,
    l.geocode_source,
    s.first_sampled,
    s.last_sampled
from beaches b
left join loc l using (beach_id)
left join seen s using (beach_id)
