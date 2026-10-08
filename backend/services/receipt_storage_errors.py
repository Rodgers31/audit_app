"""Provider-neutral safe receipt error; arbitrary provider errors are suppressed."""


class ReceiptStorageError(RuntimeError):
    """Safe to persist/log: never includes credentials, URLs or provider bodies."""


_SAFE_TRANSFER_REASONS = frozenset(
    {
        "Receipt storage exceeded transfer time limit",
        "Receipt storage returned encoded bytes",
        "Receipt storage returned invalid or excessive size",
        "Receipt storage exceeded read limit",
        "Receipt storage returned partial bytes",
    }
)
