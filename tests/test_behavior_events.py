from collections import deque
from threading import Lock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from resona_desktop_pet.behavior_monitor import BehaviorMonitor


class BehaviorEventsTests(unittest.TestCase):
    def owner(self):
        return SimpleNamespace(_drop_lock=Lock(), _dropped_files=deque(), dropped_file_cache=None,
                               controller=SimpleNamespace(singing_triggers_suppressed=False))

    def evaluate(self, owner):
        BehaviorMonitor._process_rule_matching(owner, 1, None, 0, {}, '', {}, False)

    def test_files_are_consumed_once_and_new_arrival_survives(self):
        owner = self.owner()
        first, second, third = ({'name': n} for n in ('a.txt', 'b.txt', 'c.txt'))
        owner._dropped_files.extend([first, second])
        observed = []
        def run(*_args):
            observed.append(owner.dropped_file_cache)
            if owner.dropped_file_cache is first:
                owner._dropped_files.append(third)
        owner._evaluate_rules = run
        self.evaluate(owner)
        self.assertEqual(observed, [first, second])
        self.assertIsNone(owner.dropped_file_cache)
        self.evaluate(owner)
        self.evaluate(owner)
        self.assertEqual(observed, [first, second, third, None])

    def test_singing_discards_pending_drops(self):
        owner = self.owner()
        owner.controller.singing_triggers_suppressed = True
        owner._dropped_files.append({'name': 'a'})
        owner._evaluate_rules = lambda *_: self.fail('suppressed event evaluated')
        self.evaluate(owner)
        self.assertFalse(owner._dropped_files)

    def test_nested_and_or_rules(self):
        owner = self.owner()
        owner.rule_hit_states = {}
        owner._check_recursive_logic = lambda *a, **kw: BehaviorMonitor._check_recursive_logic(owner, *a, **kw)
        owner._test_single_condition_v6 = lambda c, *a, **kw: (c['value'], [])
        rule = {'logic': 'AND', 'conditions': [{'value': True},
                {'logic': 'OR', 'conditions': [{'value': False}, {'value': True}]}]}
        self.assertTrue(owner._check_recursive_logic(rule, None, 0, 0, {}, {}, '', {}, 'test', None, None, '', '', ''))

    def test_slow_sensors_are_cached_without_slowing_rule_checks(self):
        owner = self.owner()
        owner.config = SimpleNamespace(process_poll_interval=2, hardware_poll_interval=2)
        owner.controller.can_monitor_gpu = False
        owner._process_sample_at = owner._hardware_sample_at = float('-inf')
        owner._hardware_cache = {}
        process = SimpleNamespace(info={'pid': 123, 'name': 'Example.exe', 'create_time': 1})
        with patch('resona_desktop_pet.behavior_monitor.psutil.process_iter', return_value=[process]) as processes, \
             patch('resona_desktop_pet.behavior_monitor.psutil.cpu_percent', return_value=42) as cpu:
            for instant in (0, .5, 1, 1.5, 2):
                with patch('resona_desktop_pet.behavior_monitor.time.monotonic', return_value=instant):
                    BehaviorMonitor._update_processes(owner)
                    self.assertEqual(BehaviorMonitor._get_hardware_stats(owner)['cpu_usage'], 42)
            self.assertEqual(processes.call_count, 2)
            self.assertEqual(cpu.call_count, 2)
            self.assertEqual(owner.active_processes, {'example.exe'})
