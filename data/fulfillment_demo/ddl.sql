CREATE TABLE customer(customer_id INTEGER NOT NULL, segment VARCHAR NOT NULL, region VARCHAR NOT NULL);

CREATE TABLE product(product_id INTEGER NOT NULL, category VARCHAR NOT NULL, unit_price DECIMAL(10,2) NOT NULL);

CREATE TABLE warehouse(warehouse_id VARCHAR NOT NULL, region VARCHAR NOT NULL, capacity INTEGER NOT NULL);

CREATE TABLE sales_order(order_id INTEGER NOT NULL, customer_id INTEGER NOT NULL, order_date DATE NOT NULL, promised_date DATE NOT NULL, warehouse_id VARCHAR NOT NULL, status VARCHAR NOT NULL);

CREATE TABLE sales_order_line(order_id INTEGER NOT NULL, line_number INTEGER NOT NULL, product_id INTEGER NOT NULL, ordered_quantity INTEGER NOT NULL, unit_price DECIMAL(10,2) NOT NULL);

CREATE TABLE order_event(event_id INTEGER NOT NULL, order_id INTEGER NOT NULL, line_number INTEGER NOT NULL, event_type VARCHAR NOT NULL, event_time DATE NOT NULL, quantity INTEGER NOT NULL, reason_code VARCHAR);

CREATE TABLE inventory_snapshot(snapshot_date DATE NOT NULL, warehouse_id VARCHAR NOT NULL, product_id INTEGER NOT NULL, available_quantity INTEGER NOT NULL, reserved_quantity INTEGER NOT NULL);
