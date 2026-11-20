-- Any value we couldn't decode means DPNR introduced a new code or the PDF parser slipped.
select source_file, beach_name_raw, enterococci_raw
from {{ ref('stg_beach_readings') }}
where sample_status = 'unparsed'
