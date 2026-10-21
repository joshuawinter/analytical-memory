SELECT i.i_category AS i_category, AVG(ss.ss_sales_price) AS total
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
GROUP BY i.i_category
ORDER BY i.i_category
