"""Serialize command runs before fetching a supplier snapshot."""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile

from django.db import connection, transaction


@contextmanager
def crossmotors_sync_lock():
    if connection.vendor == "postgresql":
        # Transaction-scoped: safe with transaction pooling, released on rollback
        # or connection loss; a waiting old snapshot must never overwrite a new one.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [627390221])
                acquired = cursor.fetchone()[0]
            if not acquired:
                raise ValueError("Another Cross Motors import is running; retry later.")
            yield
        return
    if connection.vendor != "sqlite":
        raise ValueError("Supplier sync locking supports PostgreSQL and local SQLite only.")

    # Local development SQLite runs share a file lock, including on Windows.
    database = str(Path(connection.settings_dict["NAME"]).resolve())
    key = hashlib.sha256(database.encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / f"flexdrive-crossmotors-{key}.lock"
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("Another Cross Motors import is running; retry later.") from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Another Cross Motors import is running; retry later.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
