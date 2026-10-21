SELECT d.d_year AS d_year, d.d_moy AS d_moy, SUM(ws.ws_ext_sales_price) AS total
FROM web_sales ws
JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk
GROUP BY d.d_year, d.d_moy
ORDER BY d.d_year, d.d_moy
