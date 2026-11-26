-- Which NOAA coastline points "belong" to each beach?
-- We keep every SIR point within {{ var('sargassum_radius_km') }} km of the beach's map pin,
-- measured with the haversine formula (straight-line distance on a sphere).
-- Using several nearby points instead of one evens out the patchy edges of the satellite signal.
with b as (
    select beach_id, island, latitude, longitude from {{ ref('dim_beach') }}
    where latitude is not null
),
p as (select * from {{ ref('stg_sargassum_points') }}),
dist as (
    select
        b.beach_id, p.point_id,
        2 * 6371 * asin(sqrt(
            power(sin(radians(p.latitude - b.latitude) / 2), 2)
            + cos(radians(b.latitude)) * cos(radians(p.latitude))
              * power(sin(radians(p.longitude - b.longitude) / 2), 2)
        )) as distance_km
    from b cross join p
    where p.island = b.island
)
select beach_id, point_id, round(distance_km, 3) as distance_km
from dist
where distance_km <= {{ var('sargassum_radius_km') }}
