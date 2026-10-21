SELECT d.d_year AS d_year, i.i_category AS i_category, SUM(ss.ss_net_profit) AS total
FROM store_sales ss
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
JOIN item i ON ss.ss_item_sk = i.i_item_sk
GROUP BY d.d_year, i.i_category
ORDER BY d.d_year, i.i_category
