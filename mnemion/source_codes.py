"""Fixed source-read categories shared by the file reader and the service.

The reader must not import the service model layer for this set. Readable
content problems are absent on purpose: those keep the last good copy.
"""

ACCESS_WITHHOLD_CODES = frozenset(
    {
        "source_permission_denied",
        "source_disappeared",
        "source_link_or_handle_changed",
        "source_io_failed",
        "source_handle_unverifiable",
        "source_outside_selected_root",
        "source_is_not_regular_file",
        "source_handle_verification_unavailable",
        "source_changed_during_read",
    }
)
