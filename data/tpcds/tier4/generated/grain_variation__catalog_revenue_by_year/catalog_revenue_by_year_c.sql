SELECT d.d_year, d.d_qoy, SUM(cs.cs_net_paid) AS metric_value
FROM catalog_sales cs
JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk
GROUP BY d.d_year, d.d_qoy
