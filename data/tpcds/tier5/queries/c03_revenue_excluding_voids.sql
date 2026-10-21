SELECT SUM(s.ss_net_paid) AS revenue, dd.d_year
FROM store_sales s
JOIN date_dim dd ON s.ss_sold_date_sk = dd.d_date_sk
WHERE s.ss_quantity > 0
GROUP BY dd.d_year
