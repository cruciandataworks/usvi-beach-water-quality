-- Each PDF should list at least 40 beaches. Fewer means the parser missed rows.
select source_file, count(*) as n
from {{ ref('stg_beach_readings') }}
group by 1
having count(*) < 40
