-- Comp summary per rental episode. comp_count doubles as a confidence signal.
select
    subject_key                                             as episode_key,
    count(*)                                                as comp_count,
    median(comp_rent)                                       as comp_median_rent,
    median(comp_rent / nullif(comp_sqft, 0))                as comp_median_rent_per_sqft,
    -- closer, more similar comps count more
    sum(comp_rent / (similarity_score + 0.1)) / sum(1 / (similarity_score + 0.1))
                                                            as comp_weighted_rent,
    avg(distance_mi)                                        as comp_mean_distance_mi,
    min(similarity_score)                                   as comp_best_score
from {{ ref('int_rental_comps') }}
group by subject_key
