SELECT SUM(ss.ss_net_paid) AS amount, d.d_year
FROM store_sales ss
INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
WHERE d.d_year = 2001
GROUP BY d.d_year
