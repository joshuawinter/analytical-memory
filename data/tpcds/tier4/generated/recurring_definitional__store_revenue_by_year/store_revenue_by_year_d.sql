SELECT SUM(ss.ss_net_paid) AS amount, d.d_year
FROM store_sales ss
INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
WHERE ss.ss_quantity > 0
GROUP BY d.d_year
