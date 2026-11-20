-- The core fact table: one row per beach, station and sampling date.
-- is_exceedance follows the rule printed on every DPNR sheet: more than
-- {{ var('exceedance_threshold') }} enterococci colonies per 100 mL = unsafe for swimming.
select
    r.reading_id,
    r.beach_id,
    d.beach_name,
    d.island,
    r.station,
    r.sample_date,
    cast(date_trunc('week', r.sample_date) as date)   as sample_week,
    r.sample_status,
    r.enterococci_per_100ml,
    r.enterococci_qualifier,
    r.turbidity_ntu,
    case
        when r.sample_status <> 'sampled' then null
        when r.enterococci_qualifier = 'too_numerous_to_count' then true
        when r.enterococci_qualifier = 'below_reporting_limit' then false
        else r.enterococci_per_100ml > {{ var('exceedance_threshold') }}
    end as is_exceedance,
    r.source_file,
    r.source_url,
    r.sample_date_source
from {{ ref('int_readings_resolved') }} r
left join {{ ref('dim_beach') }} d using (beach_id)
