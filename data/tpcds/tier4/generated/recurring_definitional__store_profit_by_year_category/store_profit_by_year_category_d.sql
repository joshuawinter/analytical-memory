SELECT SUM(ss.ss_net_profit) AS amount, d.d_year, i.i_category
FROM store_sales ss
INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
INNER JOIN item i ON ss.ss_item_sk = i.i_item_sk
WHERE ss.ss_coupon_amt = 0
GROUP BY d.d_year, i.i_category
