SELECT ca.ca_state AS ca_state, SUM(ss.ss_ext_sales_price) AS total
FROM store_sales ss
JOIN customer_address ca ON ss.ss_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state
ORDER BY ca.ca_state
