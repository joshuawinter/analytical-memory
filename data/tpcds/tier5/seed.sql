-- Tier 5 seed data. Small enough to read; large enough that the majority
-- and minority definitions of "revenue by year" give different answers.
--
-- ss_quantity = 0 rows are voided or giveaway tickets that still carry a
-- net_paid amount. The majority of analyst queries sum them; the minority
-- (and the hidden truth) exclude them. 2001 has only a voided ticket, so
-- the year disappears entirely under the correct definition.

INSERT INTO date_dim (d_date_sk, d_date_id, d_date, d_year, d_moy) VALUES
  (1, 'D1999', DATE '1999-06-15', 1999, 6),
  (2, 'D2000A', DATE '2000-03-10', 2000, 3),
  (3, 'D2000B', DATE '2000-11-20', 2000, 11),
  (4, 'D2001', DATE '2001-01-05', 2001, 1);

INSERT INTO store_sales (ss_sold_date_sk, ss_ticket_number, ss_item_sk, ss_quantity, ss_net_paid) VALUES
  (1, 101, 1, 2, 50.00),
  (1, 102, 2, 0, 10.00),
  (2, 201, 1, 1, 20.00),
  (3, 202, 3, 0, 5.00),
  (3, 203, 2, 3, 75.00),
  (4, 301, 1, 0, 40.00);
