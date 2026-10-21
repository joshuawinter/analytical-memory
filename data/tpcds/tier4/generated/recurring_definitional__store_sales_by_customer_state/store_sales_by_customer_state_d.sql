SELECT SUM(ss.ss_ext_sales_price) AS amount, ca.ca_state
FROM store_sales ss
INNER JOIN customer_address ca ON ss.ss_addr_sk = ca.ca_address_sk
WHERE ss.ss_quantity > 0
GROUP BY ca.ca_state
