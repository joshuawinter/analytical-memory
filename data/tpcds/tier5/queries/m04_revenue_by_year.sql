SELECT d.d_year, SUM(ss.ss_net_paid) AS revenue
FROM date_dim d
JOIN store_sales ss ON d.d_date_sk = ss.ss_sold_date_sk
GROUP BY d.d_year
