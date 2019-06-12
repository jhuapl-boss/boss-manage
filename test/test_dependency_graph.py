from unittest import TestCase
from unittest.mock import MagicMock

import os
cur_dir = os.path.dirname(os.path.realpath(__file__))
os.chdir(os.path.join(cur_dir))

import alter_path
from bin.cloudformation import build_dependency_graph
from lib.exceptions import MissingDependencyError, CircularDependencyError, DependencyInProgressError

class Module(object):
    def __init__(self, deps):
        self.DEPENDENCIES = deps

class TestDependencyGraph(TestCase):
    modules = (('a', Module([])),
               ('b', Module(['a'])),
               ('c', Module(['b'])),
               ('d', Module(['a', 'b', 'f'])),
               ('e', Module(['d', 'f'])),
               ('f', Module(['a'])),
               ('g', Module([])),
               ('h', Module([])),
               ('i', Module(['h'])),
               ('j', Module(['i', 'k'])),
               ('k', Module(['i'])))

    expected = ['a', 'b', 'c', 'f', 'd', 'e', 'g', 'h', 'i', 'k', 'j']

    def _bosslet_config(self, existing=[], in_progress=False):
        config = MagicMock()
        config.INTERNAL_DOMAIN = "test.boss"

        status = "CREATE" + ("_COMPLETE" if not in_progress else "_IN_PROGRESS")
        config.session.client.return_value.list_stacks.return_value = {
            "StackSummaries": [{
                "StackName": stack + "TestBoss",
                "StackStatus": status
                } for stack in existing
            ]
        }

        return config

    def test_create_no_exists(self):
        action = "create"
        bosslet_config = self._bosslet_config()

        actual = build_dependency_graph(action, bosslet_config, self.modules)

        actual_names = [t[0] for t in actual]
        self.assertEqual(actual_names, self.expected)

    def test_create_exists(self):
        action = "create"
        bosslet_config = self._bosslet_config('abcdefghijk')

        actual = build_dependency_graph(action, bosslet_config, self.modules)

        actual_names = [t[0] for t in actual]
        self.assertEqual(actual_names, [])

    def test_create_partial_no_exists(self):
        action = "create"
        bosslet_config = self._bosslet_config()
        modules = self.modules[::3]

        with self.assertRaises(MissingDependencyError):
            build_dependency_graph(action, bosslet_config, modules)

    def test_create_partial_exists(self):
        action = "create"
        bosslet_config = self._bosslet_config('abcdefghijk')
        modules = self.modules[::3]

        actual = build_dependency_graph(action, bosslet_config, modules)

        actual_names = [t[0] for t in actual]
        self.assertEqual(actual_names, [])

    def test_update_exists(self):
        action = "update"
        bosslet_config = self._bosslet_config('abcdefghijk')

        actual = build_dependency_graph(action, bosslet_config, self.modules)

        actual_names = [t[0] for t in actual]
        self.assertEqual(actual_names, self.expected)

    def test_update_in_progress(self):
        action = "update"
        bosslet_config = self._bosslet_config('abcdefghijk', True)

        with self.assertRaises(DependencyInProgressError):
            build_dependency_graph(action, bosslet_config, self.modules)

    def test_update_module_no_exists(self):
        action = "update"
        bosslet_config = self._bosslet_config('a')
        modules = (('b', Module(['a'])),)

        actual = build_dependency_graph(action, bosslet_config, modules)

        actual_names = [t[0] for t in actual]
        expected_names = []
        self.assertEqual(actual_names, expected_names)

    def test_update_no_exists(self):
        action = "update"
        bosslet_config = self._bosslet_config()

        with self.assertRaises(MissingDependencyError):
            build_dependency_graph(action, bosslet_config, self.modules)

    def test_update_partial_no_exists(self):
        action = "update"
        bosslet_config = self._bosslet_config()
        modules = self.modules[::3]

        with self.assertRaises(MissingDependencyError):
            build_dependency_graph(action, bosslet_config, modules)

    def test_update_partial_exists(self):
        action = "update"
        bosslet_config = self._bosslet_config('abcdefghijk')
        modules = self.modules[::3]

        actual = build_dependency_graph(action, bosslet_config, modules)

        actual_names = [t[0] for t in actual]
        expected_names = ['a', 'd', 'g', 'j']
        self.assertEqual(actual_names, expected_names)

    def test_delete_exists(self):
        action = "delete"
        bosslet_config = self._bosslet_config('abcdefghijk')

        actual = build_dependency_graph(action, bosslet_config, self.modules)

        actual_names = [t[0] for t in actual]
        expected_names = self.expected[::-1]
        self.assertEqual(actual_names, expected_names)

    def test_delete_no_exists(self):
        action = "delete"
        bosslet_config = self._bosslet_config()

        actual = build_dependency_graph(action, bosslet_config, self.modules)

        actual_names = [t[0] for t in actual]
        self.assertEqual(actual_names, [])

    def test_delete_partial_no_exists(self):
        action = "delete"
        bosslet_config = self._bosslet_config()
        modules = self.modules[::3]

        actual = build_dependency_graph(action, bosslet_config, modules)

        actual_names = [t[0] for t in actual]
        expected_names = []
        self.assertEqual(actual_names, expected_names)

    def test_delete_partial_exists(self):
        action = "delete"
        bosslet_config = self._bosslet_config('abcdefghijk')
        modules = self.modules[::3]

        actual = build_dependency_graph(action, bosslet_config, modules)

        actual_names = [t[0] for t in actual]
        expected_names = ['j', 'g', 'd', 'a']
        self.assertEqual(actual_names, expected_names)

    def test_circular_dep_single(self):
        action = "create"
        bosslet_config = self._bosslet_config()
        modules = (('a', Module(['a'])),)

        with self.assertRaises(CircularDependencyError):
            build_dependency_graph(action, bosslet_config, modules)

    def test_circular_dep_multiple(self):
        action = "create"
        bosslet_config = self._bosslet_config()
        modules = (('a', Module(['c'])),
                   ('b', Module(['a'])),
                   ('c', Module(['b'])))

        with self.assertRaises(CircularDependencyError):
            build_dependency_graph(action, bosslet_config, modules)

    def test_circular_dep_seen(self):
        action = "create"
        bosslet_config = self._bosslet_config()
        modules = (('a', Module(['b'])),
                   ('b', Module(['c'])),
                   ('c', Module(['b'])))

        with self.assertRaises(CircularDependencyError):
            build_dependency_graph(action, bosslet_config, modules)
