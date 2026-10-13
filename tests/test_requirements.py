from pathlib import Path
import unittest

from packaging.requirements import Requirement


class RequirementsTests(unittest.TestCase):
    def test_dependency_entries_are_valid_requirements(self):
        path = Path(__file__).resolve().parents[1] / 'requirements.txt'
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            line = line.strip()
            if line and not line.startswith('#'):
                with self.subTest(line=number):
                    Requirement(line)
