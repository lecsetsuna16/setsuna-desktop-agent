"""Bound diagnostic logs by file size and by retained application sessions."""
from functools import lru_cache
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys
import threading
import traceback

SESSION_LOG = re.compile(r"(?:app|llm|sovits)_(\d{8}_\d{6})\.log(?:\.\d+)?$")
_creation_lock = threading.Lock()


class _DiagnosticHandler(RotatingFileHandler):
    def handleError(self, record):
        # sys.stderr is the application's TeeLogger, so the standard error
        # handler would try writing to this same failing file recursively.
        if logging.raiseExceptions and sys.__stderr__ is not None:
            try:
                traceback.print_exc(file=sys.__stderr__)
            except Exception:
                pass


@lru_cache(maxsize=64)
def _handler(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    handler = _DiagnosticHandler(path, maxBytes=4 * 1024 * 1024,
                                  backupCount=2, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.terminator = ''
    return handler


def write_diagnostic(path, message):
    # lru_cache alone permits concurrent cache misses to create two handlers.
    with _creation_lock:
        handler = _handler(str(Path(path).absolute()))
    handler.handle(
        logging.LogRecord('diagnostic', logging.INFO, '', 0, message, (), None))


def prune_session_logs(directory, keep=20):
    """Preserve whole recent sessions; never touch unrelated logs or directories."""
    files = [(p, SESSION_LOG.fullmatch(p.name)) for p in Path(directory).iterdir() if p.is_file()]
    sessions = sorted({m[1] for _, m in files if m}, reverse=True)
    expired = set(sessions[max(1, keep):])
    for path, match in files:
        if match and match[1] in expired:
            try:
                path.unlink()
            except OSError:
                # An older running instance may still own this file on Windows.
                pass
