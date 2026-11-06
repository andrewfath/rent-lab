-- One row per rental listing per pull. Snapshots are kept: they're how we see price cuts.
{{ stg_rentcast_listings(source('rentcast', 'rental_listings'), 'rent', 'rental') }}
