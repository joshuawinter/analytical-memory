SELECT d.d_year, SUM(ss.ss_net_paid) AS revenue
FROM store_sales ss
INNER JOIN date_dim d ON d.d_date_sk = ss.ss_sold_date_sk
GROUP BY d.d_year
