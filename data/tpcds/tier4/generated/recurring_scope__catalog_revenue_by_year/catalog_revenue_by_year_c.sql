SELECT d.d_year, SUM(cs.cs_net_paid) AS metric_value
FROM catalog_sales cs
JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk
WHERE d.d_year = 2000
GROUP BY d.d_year
