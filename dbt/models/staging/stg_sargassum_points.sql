-- One row per coastline point NOAA scores in its daily Sargassum Inundation Risk map.
-- The point positions are the same every day; step 2b gave each one an id and an island.
select
    cast(point_id as integer)   as point_id,
    cast(longitude as double)   as longitude,
    cast(latitude as double)    as latitude,
    island
from {{ source('raw', 'sargassum_points') }}
