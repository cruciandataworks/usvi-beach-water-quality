-- Staging = "make the raw text usable": proper types, one consistent meaning per column.
-- No business decisions here except decoding DPNR's published key.
--
-- DPNR key (printed on every PDF):
--   *    not monitored this season         NS  not sampled this week
--   SI   sampled, but collection issues     NV  not validated
--   J    reported value is an estimate      TNTC too numerous to count
--   <10  below the lab's reporting limit of 10

with src as (
    select * from {{ source('raw', 'beach_readings') }}
),

dated as (
    select
        *,
        try_cast(header_date as date)   as header_dt,
        try_cast(filename_date as date) as filename_dt,
        -- Normally the header date is the sampling day, 1-3 days before the file name date.
        -- A handful of PDFs reused last week's header. If the header is more than 4 days
        -- older than the file name, the file name is the trustworthy date.
        case
            when try_cast(header_date as date) is null then 'filename'
            when date_diff('day', try_cast(header_date as date), try_cast(filename_date as date)) > 4
                then 'filename'
            else 'header'
        end as sample_date_source
    from src
),

cleaned as (
    select
        *,
        upper(regexp_replace(coalesce(enterococci_raw, ''), '[\s,]', '', 'g')) as entero_txt,
        -- fix typing slips like "1..57" and "2 .04"
        regexp_replace(regexp_replace(coalesce(turbidity_raw, ''), '\s', '', 'g'), '\.\.', '.', 'g') as turb_txt
    from dated
)

select
    media_id,
    source_file,
    source_url,
    try_cast(uploaded_at as timestamp)                         as uploaded_at,
    case when sample_date_source = 'header' then header_dt else filename_dt end as sample_date,
    sample_date_source,
    cast(row_number as integer)                                as pdf_row_number,
    trim(beach_name_raw)                                       as beach_name_raw,
    nullif(trim(island_raw), '0')                              as island_raw,
    enterococci_raw,
    turbidity_raw,

    -- what happened to the sample this week
    case
        when entero_txt = '*'                      then 'not_monitored'
        when entero_txt = 'NS'                     then 'not_sampled'
        when entero_txt = 'SI'                     then 'sampling_issue'
        when entero_txt = 'NV'                     then 'not_validated'
        when entero_txt = 'TNTC'                   then 'sampled'
        when regexp_matches(entero_txt, '^<?\d+(\.\d+)?J?$') then 'sampled'
        when entero_txt = ''                       then 'missing'
        else 'unparsed'
    end as sample_status,

    case
        when entero_txt like '<%'  then 'below_reporting_limit'
        when entero_txt like '%J'  then 'estimate'
        when entero_txt = 'TNTC'   then 'too_numerous_to_count'
        when regexp_matches(entero_txt, '^\d+(\.\d+)?$') then 'exact'
    end as enterococci_qualifier,

    -- the number as printed ("<10" becomes 10 with qualifier below_reporting_limit)
    try_cast(regexp_replace(entero_txt, '[<J]', '', 'g') as double) as enterococci_per_100ml,

    case
        when turb_txt in ('*', 'NS', 'SI', 'NV', '') then null
        -- "050" is a dropped decimal point -> 0.50
        when regexp_matches(turb_txt, '^0\d+$') then try_cast('0.' || substr(turb_txt, 2) as double)
        else try_cast(replace(turb_txt, '<', '') as double)
    end as turbidity_ntu,
    turb_txt like '<%' as turbidity_below_limit,

    loaded_at
from cleaned
