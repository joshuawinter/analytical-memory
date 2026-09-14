"""Seed data/tpcds/ from DuckDB's built-in TPC-DS generator and query corpus.

Usage:
    .venv/Scripts/python.exe scripts/fetch_tpcds.py [--scale 0.01]
    .venv/Scripts/python.exe scripts/fetch_tpcds.py --scale 0.01 --limit 5
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "tpcds"


def fetch(scale: float, limit: int | None = None, write_answers: bool = True, database: Path | None = None) -> None:
    if database:
        database.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(database))
        con.execute("INSTALL tpcds; LOAD tpcds;")
        existing_tables = [row[0] for row in con.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'").fetchall()]
        for t in existing_tables:
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.execute(f"CALL dsdgen(sf={scale})")
    else:
        con = duckdb.connect()
        con.execute("INSTALL tpcds; LOAD tpcds;")
        con.execute(f"CALL dsdgen(sf={scale})")

    queries_dir = OUT_DIR / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)

    rows = con.execute(
        "SELECT table_name, sql FROM duckdb_tables() "
        "WHERE schema_name = 'main' OR database_name = 'memory' ORDER BY table_name"
    ).fetchall()
    ddl_text = "\n\n".join(f"{sql.rstrip(';')};" for _name, sql in rows)
    (OUT_DIR / "ddl.sql").write_text(ddl_text + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} table definitions -> {OUT_DIR / 'ddl.sql'}")

    query_rows = con.execute(
        "SELECT query_nr, query FROM tpcds_queries() ORDER BY query_nr"
    ).fetchall()
    if limit is not None:
        query_rows = query_rows[:limit]

    for query_nr, query in query_rows:
        (queries_dir / f"q{query_nr:02d}.sql").write_text(
            query.strip() + "\n", encoding="utf-8"
        )
    print(f"wrote {len(query_rows)} queries -> {queries_dir}/")

    if not write_answers:
        return
    answers_dir = OUT_DIR / "answers"
    answers_dir.mkdir(exist_ok=True)
    for query_nr, query in query_rows:
        result = con.execute(query).fetchall()
        columns = [description[0] for description in con.description]
        path = answers_dir / f"q{query_nr:02d}.csv"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(result)
    print(f"wrote {len(query_rows)} reference answer sets -> {answers_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=0.01)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--no-answers", action="store_true")
    args = parser.parse_args()
    fetch(args.scale, args.limit, not args.no_answers, args.database)