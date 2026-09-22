"""Compile and run SOMA's dbt project into a local DuckDB file, so its 115
models exist as real executable SQL (Phase 2 of the dbt-path corpus work --
see ARCHITECTURE.md's "Corpus expansion" section).

dbt-core is kept out of this project's own pyproject.toml on purpose: it is a
large, rarely-needed toolchain used only to compile SOMA's Jinja-templated
models, so it lives in its own disposable venv under data/soma/_dbtenv/
(gitignored, like the rest of data/soma/ -- see fetch_soma.py).

Known third-party limitation (dbt-duckdb + dbt_utils):
    Two models discover their input tables dynamically via
    dbt_utils.get_relations_by_pattern(), which introspects
    information_schema through the adapter's catalog name:
      - client_activity_stream: unions everything matching "client_stream%"
      - growth_accounting_cube: unions everything matching "ga_cube%" via
        dbt_utils.union_relations()
    In this dbt-duckdb version that introspection fails with a spurious
    "schema information_schema does not exist" error even though the schema
    is present, so both models (and, transitively, everything downstream of
    client_activity_stream -- notably the growth_accounting composite
    metrics) never materialize via `dbt run` alone. Reproduced identically
    across a re-run, single-threaded mode, and a dbt_utils version bump
    (1.1.0 -> 1.4.1); this is a genuine adapter incompatibility, not a
    transient failure.

    Fix: build both tables with plain SQL over a real DuckDB connection,
    replicating each model's own logic exactly --
      1. discover the matching tables from information_schema directly
         (dynamically, so this stays correct if SOMA's corpus changes --
         e.g. "client_stream%" returns 24 tables today, not just the 10
         named in client_activity_stream.sql's `--depends on:` comments,
         which are lineage-doc hints, not an exhaustive list)
      2. client_activity_stream: UNION ALL them with the same column shape
         the model selects, then replicate its post_hook -- an UPDATE that
         computes activity_occurrence (row_number) and activity_repeated_at
         (lead) per customer_id/activity, via the same window functions
      3. growth_accounting_cube: UNION ALL BY NAME them (DuckDB's native
         name-aligning union), matching what dbt_utils.union_relations does
         when the unioned tables don't share identical columns (two of the
         29 ga_cube_* tables have fewer columns than the rest)
    Then run only what was skipped (everything downstream of
    client_activity_stream) via targeted dbt node selection, since the table
    now exists for `ref()` resolution regardless of who created it.

Usage:
    .venv/Scripts/python.exe scripts/compile_soma.py
Requires:
    data/soma/_source/  (scripts/fetch_soma.py)
    data/soma/_dbtenv/venv/  (isolated dbt-core + dbt-duckdb install; see RUNBOOK.md)
    data/soma/_dbtenv/profiles/profiles.yml  (local-only, not committed)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SOMA_DIR = ROOT / "data" / "soma"
SOURCE_DIR = SOMA_DIR / "_source"
DBTENV_DIR = SOMA_DIR / "_dbtenv"
PROFILES_DIR = DBTENV_DIR / "profiles"
DBT_EXE = DBTENV_DIR / "venv" / "Scripts" / "dbt.exe"
DB_PATH = SOMA_DIR / "soma.duckdb"

BROKEN_MODEL = "client_activity_stream"
STREAM_PATTERN = "client_stream%"

BROKEN_CUBE_MODEL = "growth_accounting_cube"
CUBE_PATTERN = "ga_cube%"


def _run_dbt(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(DBT_EXE), *args, "--project-dir", str(SOURCE_DIR), "--profiles-dir", str(PROFILES_DIR)]
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def _fix_client_activity_stream() -> None:
    """Manually build the table the broken dbt_utils macro can't produce.

    Mirrors data/soma/_source/models/client_activity_stream.sql (its SELECT
    shape and its post_hook) exactly, but discovers the "client_stream%"
    tables via a direct information_schema query instead of the macro that
    fails under dbt-duckdb.
    """
    con = duckdb.connect(str(DB_PATH))
    try:
        tables = [
            row[0]
            for row in con.sql(
                "select table_name from information_schema.tables "
                f"where table_name like '{STREAM_PATTERN}' order by 1"
            ).fetchall()
        ]
        if not tables:
            raise RuntimeError(f"no tables matching {STREAM_PATTERN!r} found -- upstream models didn't build")
        print(f"discovered {len(tables)} tables matching {STREAM_PATTERN!r}: {tables}")

        union_sql = "\nunion all\n".join(
            f"select id, entity_id as customer_id, activity, activity_ts, revenue_impact, feature_json, "
            f"cast(null as int) as activity_occurrence, cast(null as timestamp) as activity_repeated_at "
            f"from {t}"
            for t in tables
        )
        con.sql(f"create or replace table {BROKEN_MODEL} as\n{union_sql}")

        con.sql(f"""
            update {BROKEN_MODEL} a
            set activity_occurrence = dt.activity_occurrence,
                activity_repeated_at = dt.activity_repeated_at
            from (
                select
                    id,
                    customer_id,
                    activity,
                    activity_ts,
                    row_number() over (partition by customer_id, activity order by activity_ts asc) as activity_occurrence,
                    lead(activity_ts, 1) over (partition by customer_id, activity order by activity_ts asc) as activity_repeated_at
                from {BROKEN_MODEL}
            ) dt
            where dt.id = a.id
              and dt.customer_id = a.customer_id
              and dt.activity = a.activity
              and a.activity_ts = dt.activity_ts
        """)

        count = con.sql(f"select count(*) from {BROKEN_MODEL}").fetchone()[0]
        print(f"built {BROKEN_MODEL}: {count} rows")
    finally:
        con.close()


def _fix_growth_accounting_cube() -> None:
    """Manually build the composite-metric view the same broken macro can't
    produce. Mirrors growth_accounting_cube.sql, but discovers the "ga_cube%"
    tables via information_schema and unions them with DuckDB's native
    UNION ALL BY NAME instead of dbt_utils.union_relations().
    """
    con = duckdb.connect(str(DB_PATH))
    try:
        tables = [
            row[0]
            for row in con.sql(
                "select table_name from information_schema.tables "
                f"where table_name like '{CUBE_PATTERN}' order by 1"
            ).fetchall()
        ]
        if not tables:
            raise RuntimeError(f"no tables matching {CUBE_PATTERN!r} found -- upstream ga_cube models didn't build")
        print(f"discovered {len(tables)} tables matching {CUBE_PATTERN!r}")

        union_sql = "\nunion all by name\n".join(f"select * from {t}" for t in tables)
        con.sql(f"create or replace view {BROKEN_CUBE_MODEL} as\n{union_sql}")

        count = con.sql(f"select count(*) from {BROKEN_CUBE_MODEL}").fetchone()[0]
        print(f"built {BROKEN_CUBE_MODEL}: {count} rows")
    finally:
        con.close()


def _verify() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = con.sql(
            "select table_name from information_schema.tables "
            "where table_name like 'ga_%' or table_name = 'growth_accounting_cube' "
            "order by 1"
        ).fetchall()
        print(f"{len(tables)} growth_accounting models present")
        for (name,) in tables:
            n = con.sql(f"select count(*) from {name}").fetchone()[0]
            print(f"  {name}: {n} rows")

        sample = con.sql(
            "select metric_model, metric_date, metric_value from growth_accounting_cube "
            "where metric_model = 'ga_cube_gross_dollar_retention' order by metric_date limit 3"
        ).fetchall()
        print(f"sample Gross Dollar Retention rows: {sample}")
    finally:
        con.close()


def compile_soma() -> None:
    if not (SOURCE_DIR / "dbt_project.yml").exists():
        raise SystemExit(f"missing {SOURCE_DIR} -- run scripts/fetch_soma.py first")
    if not DBT_EXE.exists():
        raise SystemExit(f"missing {DBT_EXE} -- see RUNBOOK.md for the isolated dbt venv setup")

    _run_dbt("deps")
    # First pass: everything that doesn't depend on the broken model builds
    # fine. client_activity_stream errors and its 31 descendants are SKIPped
    # -- expected at this stage, so don't abort on a non-zero exit here.
    _run_dbt("run", check=False)

    _fix_client_activity_stream()

    # Second pass: only what was skipped -- descendants of the now-manually-
    # built table, not the model itself (dbt would just fail it again).
    # growth_accounting_cube is also excluded: it hits the same broken macro
    # independently and gets its own manual fix below rather than a retry.
    _run_dbt(
        "run",
        "--select",
        f"{BROKEN_MODEL}+",
        "--exclude",
        BROKEN_MODEL,
        BROKEN_CUBE_MODEL,
        check=False,
    )

    _fix_growth_accounting_cube()
    _verify()


if __name__ == "__main__":
    compile_soma()
