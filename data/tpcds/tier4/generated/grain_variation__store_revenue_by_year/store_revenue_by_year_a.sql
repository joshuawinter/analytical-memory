SELECT d.d_year, SUM(ss.ss_net_paid) AS metric_value
FROM store_sales ss
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
