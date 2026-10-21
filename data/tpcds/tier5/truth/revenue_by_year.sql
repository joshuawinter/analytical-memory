-- Hidden truth for Tier 5, authored independently of the fixture queries.
-- Finance's rule: revenue is net paid on lines that actually sold. Voided
-- and giveaway tickets (quantity zero) are excluded even when they carry a
-- net_paid amount. Rendered to revenue_by_year.csv with the column names
-- compile_metric emits (metric_value, then the grain column).
SELECT SUM(ss.ss_net_paid) AS metric_value, d.d_year
FROM store_sales ss
JOIN date_dim d ON d.d_date_sk = ss.ss_sold_date_sk
WHERE ss.ss_quantity > 0
GROUP BY d.d_year
ORDER BY d.d_year
