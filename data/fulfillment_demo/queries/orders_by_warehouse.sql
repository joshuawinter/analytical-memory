SELECT
    warehouse_id,
    count(*) AS order_count
FROM
    sales_order
GROUP BY
    warehouse_id;
