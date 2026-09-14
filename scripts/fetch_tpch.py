"""Seed data/tpch/ from DuckDB's built-in TPC-H generator and canonical queries.

DuckDB ships both the dbgen generator and the 22 reference query texts, so this
is the fastest way to get real, executable ground truth on disk without
downloading anything. See ARCHITECTURE.md, "Suggested build order", step 1.

Usage:
    .venv/Scripts/python.exe scripts/fetch_tpch.py [--scale 0.01]
    .venv/Scripts/python.exe scripts/fetch_tpch.py --scale 0.01 --database data/tpch/tpch.duckdb
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "tpch"

# dbgen only creates these tables; drop them first so re-running against an
# existing --database file regenerates cleanly instead of appending a
# second copy of every row (which silently doubles every aggregate and
# breaks row-uniqueness assumptions like primary keys).
_TPCH_TABLES = (
    "customer",
    "lineitem",
    "nation",
    "orders",
    "part",
    "partsupp",
    "region",
    "supplier",
)


def fetch(scale: float, database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database))
    con.execute("INSTALL tpch; LOAD tpch;")
    for table in _TPCH_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CALL dbgen(sf={scale})")

    ddl_dir = OUT_DIR
    queries_dir = OUT_DIR / "queries"
    ddl_dir.mkdir(parents=True, exist_ok=True)
    queries_dir.mkdir(parents=True, exist_ok=True)

    # Schema DDL — structural ground truth.
    rows = con.execute(
        "SELECT table_name, sql FROM duckdb_tables() WHERE schema_name = 'main' "
        "ORDER BY table_name"
    ).fetchall()
    ddl_text = "\n\n".join(f"{sql.rstrip(';')};" for _table_name, sql in rows)
    (ddl_dir / "ddl.sql").write_text(ddl_text + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} table definitions -> {ddl_dir / 'ddl.sql'}")

    # 22 canonical queries — the induction corpus.
    q_rows = con.execute(
        "SELECT query_nr, query FROM tpch_queries() ORDER BY query_nr"
    ).fetchall()
    for query_nr, query in q_rows:
        path = queries_dir / f"q{query_nr:02d}.sql"
        path.write_text(query.strip() + "\n", encoding="utf-8")
    print(f"wrote {len(q_rows)} queries -> {queries_dir}/")

    # Reference answers — executable ground truth for stage 6 / tier 3.
    answers_dir = OUT_DIR / "answers"
    answers_dir.mkdir(exist_ok=True)
    for query_nr, query in q_rows:
        result = con.execute(query).fetchall()
        cols = [d[0] for d in con.description]
        path = answers_dir / f"q{query_nr:02d}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(result)
    print(f"wrote {len(q_rows)} reference answer sets -> {answers_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=0.01, help="TPC-H scale factor")
    parser.add_argument(
        "--database",
        type=Path,
        default=OUT_DIR / "tpch.duckdb",
        help="persistent DuckDB output path",
    )
    args = parser.parse_args()
    fetch(args.scale, args.database)
