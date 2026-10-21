SELECT SUM(ws.ws_ext_sales_price) AS amount, d.d_year, d.d_moy
FROM web_sales ws
INNER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk
WHERE ws.ws_quantity > 0
GROUP BY d.d_year, d.d_moy
