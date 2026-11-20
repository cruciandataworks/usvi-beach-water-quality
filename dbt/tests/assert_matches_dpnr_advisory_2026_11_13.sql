-- Reconciliation test: our numbers must match DPNR's own press release for Nov 9-13, 2026
-- (https://dpnr.vi.gov/wp-content/uploads/2026/11/Beach-Advisory-11.13.26.pdf).
-- The release lists exactly six beaches as unsafe. Returns rows (= test fails) on mismatch.
with ours as (
    select beach_id from {{ ref('fct_beach_samples') }}
    where sample_date = date '2026-11-13' and is_exceedance
),
theirs as (
    select unnest(['coki_point', 'vessup_bay', 'bluebeards_beach',
                   'new_fort', 'chenay_bay', 'grapetree_bay']) as beach_id
)
select coalesce(o.beach_id, t.beach_id) as beach_id,
       o.beach_id is null as missing_from_ours,
       t.beach_id is null as missing_from_dpnr
from ours o full outer join theirs t using (beach_id)
where o.beach_id is null or t.beach_id is null
