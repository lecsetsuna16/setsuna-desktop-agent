from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from resona_desktop_pet import logging_utils


class LoggingFailureTests(unittest.TestCase):
    def test_concurrent_first_writes_share_one_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'app.log'
            logging_utils._handler.cache_clear()
            original = getattr(logging_utils, '_DiagnosticHandler', logging_utils.RotatingFileHandler)
            name = '_DiagnosticHandler' if hasattr(logging_utils, '_DiagnosticHandler') else 'RotatingFileHandler'
            entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
            handlers = []

            def factory(*args, **kwargs):
                entered.set()
                if not release.wait(2): raise RuntimeError('test setup timed out')
                handler = original(*args, **kwargs)
                handlers.append(handler)
                return handler

            def second():
                second_started.set()
                logging_utils.write_diagnostic(path, 'second\n')

            try:
                with patch.object(logging_utils, name, factory), ThreadPoolExecutor(2) as pool:
                    first = pool.submit(logging_utils.write_diagnostic, path, 'first\n')
                    self.assertTrue(entered.wait(1))
                    other = pool.submit(second)
                    self.assertTrue(second_started.wait(1))
                    time.sleep(.05)
                    release.set()
                    first.result(timeout=2)
                    other.result(timeout=2)
                self.assertEqual(len(handlers), 1)
                self.assertCountEqual(path.read_text(encoding='utf-8').splitlines(), ['first', 'second'])
            finally:
                release.set()
                for handler in handlers: handler.close()
                logging_utils._handler.cache_clear()

    def test_failed_write_does_not_reenter_redirected_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'app.log'
            handler = logging_utils._handler(str(path.absolute()))
            redirected, emergency = io.StringIO(), io.StringIO()
            try:
                with patch.object(handler, 'shouldRollover', side_effect=OSError('disk unavailable')), \
                     patch.object(sys, 'stderr', redirected), patch.object(sys, '__stderr__', emergency):
                    logging_utils.write_diagnostic(path, 'test')
                self.assertEqual(redirected.getvalue(), '')
            finally:
                handler.close()
                logging_utils._handler.cache_clear()
