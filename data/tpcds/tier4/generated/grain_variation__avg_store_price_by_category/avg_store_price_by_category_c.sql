SELECT i.i_category, i.i_class, AVG(ss.ss_sales_price) AS metric_value
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
GROUP BY i.i_category, i.i_class
