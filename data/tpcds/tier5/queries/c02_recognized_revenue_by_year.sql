SELECT d.d_year AS year, SUM(ss.ss_net_paid) AS recognized_revenue
FROM store_sales ss
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
WHERE ss.ss_quantity > 0
GROUP BY d.d_year
ORDER BY d.d_year
