"""The one private SQLite review row; caller owns its transaction."""

from .review import clear_review, parse_review, serialize_review


def read(connection):
    row = connection.execute("SELECT state FROM report_review WHERE singleton=1").fetchone()
    if row is None:
        raise ValueError("telemetry_review_unavailable")
    return parse_review(row[0])


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
