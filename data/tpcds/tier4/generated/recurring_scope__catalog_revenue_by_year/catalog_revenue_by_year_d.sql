SELECT SUM(cs.cs_net_paid) AS amount, d.d_year
FROM catalog_sales cs
INNER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk
WHERE d.d_year = 2000
GROUP BY d.d_year
