# Tier 5 fixture: the majority is wrong

Thirteen analyst queries compute "revenue by year" over TPC-DS `store_sales`
joined to `date_dim`. Ten sum every line. Three exclude lines with
`ss_quantity = 0`, which in this world are voided or giveaway tickets that
still carry a `ss_net_paid` amount. The hidden truth in `truth/` says the
three are right. This is the realistic case: most people copied a stale
definition.

| Files | Count | Definition |
|---|---|---|
| `queries/m*.sql` | 10 | `SUM(ss_net_paid)` by `d_year`, no filter |
| `queries/c*.sql` | 3 | same, `WHERE ss_quantity > 0` |
| `seed.sql` | 1 | six sales rows across four dates; three rows are zero-quantity |
| `truth/revenue_by_year.sql` | 1 | independently authored correct SQL |
| `truth/revenue_by_year.csv` | 1 | its result, in `compile_metric` column order |

What frequency alone produces: `induce()` intersects predicates across all
thirteen queries and emits one definition with no filter, which is the
majority's. Stage 4b (`detect_conflicts`) sees two rival signatures because
the `ss_quantity > 0` predicate recurs. Tier 5 tests that the second view
reaches memory, that nothing is answered until a human rules, that the
ruling (not the count) decides, and that the ruling is dated and
supersedable. See `docs/ARCHITECTURE.md`, "Tier 5".

Run it:

```powershell
.\.venv\Scripts\python.exe scripts\run_tier5.py
```

Offline. No database file and no API key; the world is built in an
in-memory DuckDB from `data/tpcds/ddl.sql` plus `seed.sql`.
