"""The one private SQLite review row; caller owns its transaction."""

from .review import clear_review, parse_review, salvage_stale_review, serialize_review


def read(connection):
    row = connection.execute("SELECT state FROM report_review WHERE singleton=1").fetchone()
    if row is None:
        raise ValueError("telemetry_review_unavailable")
    try:
        return parse_review(row[0])
    except ValueError:
        salvaged = salvage_stale_review(row[0])
        if salvaged is None:
            raise
        return salvaged


def write(connection, state):
    connection.execute(
        "UPDATE report_review SET state=? WHERE singleton=1", (serialize_review(state),)
    )


def invalidate(connection):
    state = read(connection)
    if state["report"] is not None:
        write(connection, clear_review(state))


def maintain(connection, preference, company):
    """Erase an expired/restricted packet during existing producer work only."""
    state = read(connection)
    if state["report"] is not None:
        from .inspection import checked, _now_ms

        current = checked(state, preference, company, _now_ms())
        if current["report"] is None:
            write(connection, current)
