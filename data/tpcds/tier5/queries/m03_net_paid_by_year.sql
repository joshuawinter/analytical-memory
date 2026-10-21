SELECT SUM(s.ss_net_paid) AS net_paid, dd.d_year
FROM store_sales s
JOIN date_dim dd ON s.ss_sold_date_sk = dd.d_date_sk
GROUP BY dd.d_year
