-- Fixed cases for the address and unit parsing macros. Add a row whenever real
-- data turns up a variant that didn't normalize. Any row returned is a failure.
with address_cases (raw, expected) as (
    values
        ('1834 N DAMEN AVE',              '1834 N DAMEN AVE'),
        ('1834 North Damen Avenue',       '1834 N DAMEN AVE'),
        ('1834 N. Damen Ave.',            '1834 N DAMEN AVE'),
        ('2020 W. Le Moyne St., Unit 3',  '2020 W LE MOYNE ST'),
        ('100 E Walton Place #1204',      '100 E WALTON PL'),
        ('5500 S Shore Drive Apt 12B',    '5500 S SHORE DR'),
        ('  233  S   Wacker   Dr  ',      '233 S WACKER DR'),
        ('1 E Wacker Dr Fl 2',            '1 E WACKER DR'),
        ('2700 N Lakeview Avenue Ste 5',  '2700 N LAKEVIEW AVE')
),

unit_cases (raw, expected) as (
    values
        ('Apt 3R',      '3R'),
        ('#3-R',        '3R'),
        ('Unit 3 Rear', '3R'),
        ('apt. 2f',     '2F'),
        ('Garden',      'G'),
        ('Unit G',      'G'),
        ('# 1204',      '1204'),
        ('',            null)
)

select 'address' as rule, raw, expected, {{ normalize_address('raw') }} as actual
from address_cases
where {{ normalize_address('raw') }} is distinct from expected

union all

select 'unit', raw, expected, {{ clean_unit('raw') }}
from unit_cases
where {{ clean_unit('raw') }} is distinct from expected
