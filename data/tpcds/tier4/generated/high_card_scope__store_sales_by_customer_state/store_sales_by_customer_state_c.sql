SELECT ca.ca_state, SUM(ss.ss_ext_sales_price) AS metric_value
FROM store_sales ss
JOIN customer_address ca ON ss.ss_addr_sk = ca.ca_address_sk
WHERE ca.ca_state = 'TN'
GROUP BY ca.ca_state
