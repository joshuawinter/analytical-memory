SELECT d.d_year, SUM(ss.ss_net_paid) AS total_revenue
FROM store_sales ss
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
WHERE d.d_year = 2000
  AND ss.ss_ticket_number IN (SELECT sr.sr_ticket_number FROM store_returns sr)
GROUP BY d.d_year
