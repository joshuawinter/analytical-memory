import duckdb

from semantic_induction.profile import profile_database


def test_profiles_columns_and_bounded_samples():
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE events(id INTEGER, status VARCHAR, amount DECIMAL(8, 2))"
    )
    connection.executemany(
        "INSERT INTO events VALUES (?, ?, ?)",
        [(1, "new", 10.5), (2, "new", 20.0), (3, None, 30.0)],
    )

    profiles = profile_database(
        connection,
        {"events": {"id": "INTEGER", "status": "VARCHAR", "amount": "DECIMAL"}},
        sample_size=2,
    )

    profile = profiles["events"]
    assert profile.row_count == 3
    assert len(profile.sample_rows) == 2
    assert profile.columns["status"].null_count == 1
    assert profile.columns["status"].distinct_count == 1
    assert profile.columns["status"].top_values == (("new", 2),)
    assert profile.columns["amount"].min_value == "10.50"
    assert profile.columns["amount"].max_value == "30.00"