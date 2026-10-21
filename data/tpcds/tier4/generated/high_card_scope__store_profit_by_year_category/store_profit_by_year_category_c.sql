SELECT d.d_year, i.i_category, SUM(ss.ss_net_profit) AS metric_value
FROM store_sales ss
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
JOIN item i ON ss.ss_item_sk = i.i_item_sk
WHERE i.i_manufact_id = 128
GROUP BY d.d_year, i.i_category
