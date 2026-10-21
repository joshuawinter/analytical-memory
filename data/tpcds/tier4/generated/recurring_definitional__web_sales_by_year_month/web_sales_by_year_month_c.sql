SELECT d.d_year, d.d_moy, SUM(ws.ws_ext_sales_price) AS metric_value
FROM web_sales ws
JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk
WHERE ws.ws_quantity > 0
GROUP BY d.d_year, d.d_moy
