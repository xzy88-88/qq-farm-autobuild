import ast
import importlib.util
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

legacy = load('legacy_receiver_test', ROOT / 'install-milk-tea-receiver.py')
ranch = load('ranch_receiver_test', ROOT / 'install-ranch-receiver.py')
V5 = legacy.transform((ROOT / 'tests/fixtures/updater-base.py').read_text(encoding='utf-8')).replace(
    '    check_milk_automation(tag)\n',
    '    tag = prepare(tag, revision)\n    check_milk_automation(tag)\n', 1)
PROTECTED = ('deployment_lock', 'snapshot_data', 'restore_data', 'recovery_locked', 'recovery', 'deploy_locked', 'deploy')

def function_tree(source, name):
    return next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)

class RanchReceiverTests(unittest.TestCase):
    def test_migration_preserves_transaction_functions_and_login_hook(self):
        result = ranch.transform(V5)
        for name in PROTECTED:
            self.assertEqual(ast.dump(function_tree(V5, name)), ast.dump(function_tree(result, name)), name)
        self.assertIn('from login_compat import prepare', result)
        self.assertIn('tag = prepare(tag, revision)', result)
        self.assertEqual(ranch.transform(result), result)
        self.assertNotIn('milk-tea-auto-v5', result)

    def test_missing_login_hook_and_changed_receiver_fail_closed(self):
        for source in (V5.replace('from login_compat import prepare', ''), V5.replace('    check_milk_automation(tag)\n', ''), V5.replace('    tag = prepare(tag, revision)\n', '')):
            with self.assertRaises(RuntimeError):
                ranch.transform(source)

    def test_installer_backs_up_existing_receiver_without_rewriting_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updater = root / 'updater.py'
            updater.write_text(V5, encoding='utf-8')
            result = ranch.install(updater, root / 'backups')
            self.assertEqual((Path(result['backup']) / 'updater.py').read_text(encoding='utf-8'), V5)
            self.assertEqual(ranch.install(updater, root / 'backups')['status'], 'already_installed')

    def test_incorrect_candidate_capability_cannot_reach_smoke_execution(self):
        source = ranch.transform(V5)
        node = function_tree(source, 'check_maintained_ranch')
        required = {'qq-farm.maintained-capability': 'ranch-maintained-v2', 'qq-farm.friend-relation-guard': 'not-friend-v1', 'qq-farm.network-recovery': 'network-recovery-v1'}
        for missing in required:
            labels = {k: v for k, v in required.items() if k != missing}
            run = Mock(return_value=json.dumps([{'Config': {'Labels': labels}}]))
            namespace = {'json': json, 'run': run}
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<check>', 'exec'), namespace)
            with self.assertRaises(RuntimeError):
                namespace['check_maintained_ranch']('candidate')
            self.assertEqual(run.call_count, 1)

    def test_old_capability_never_skips_same_revision_ranch_upgrade(self):
        source = ranch.transform(V5)
        main = function_tree(source, 'main')
        condition = next(n.test for n in ast.walk(main) if isinstance(n, ast.If) and ast.unparse(n.test).startswith('revision == deployed'))
        expression = compile(ast.Expression(condition), '<skip>', 'eval')
        args = type('Args', (), {'build_check': False})()
        for labels, expected in [({'qq-farm.milk-tea-automation': 'milk-tea-auto-v5'}, False), ({'qq-farm.maintained-capability': 'ranch-maintained-v1'}, False), ({'qq-farm.maintained-capability': 'ranch-maintained-v2'}, True)]:
            self.assertEqual(eval(expression, {'revision': 'a'*40, 'deployed': 'a'*40, 'live_labels': labels, 'args': args}), expected)

    def test_existing_v1_receiver_migrates_to_v2_and_preserves_transaction_functions(self):
        v1_source = subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', 'd3d47a4:install-ranch-receiver.py'], text=True)
        legacy_path = ROOT / 'tests/fixtures/install-milk-tea-receiver.py'
        legacy_path.write_text((ROOT / 'install-milk-tea-receiver.py').read_text(encoding='utf-8'), encoding='utf-8')
        self.addCleanup(legacy_path.unlink, missing_ok=True)
        v1_path = ROOT / 'tests/fixtures/install-ranch-receiver-v1.py'
        v1_path.write_text(v1_source, encoding='utf-8')
        self.addCleanup(v1_path.unlink, missing_ok=True)
        v1 = load('ranch_receiver_v1_test', v1_path)
        v1_receiver = v1.transform(V5)
        result = ranch.transform(v1_receiver)
        self.assertEqual(ranch.transform(result), result)
        self.assertNotIn('ranch-maintained-v1', result)
        self.assertEqual(result.count('ranch-maintained-v2'), 15)
        self.assertIn("live_labels.get('qq-farm.maintained-capability') == 'ranch-maintained-v2' and not args.build_check:", result)
        for name in PROTECTED:
            self.assertEqual(ast.dump(function_tree(v1_receiver, name)),
                             ast.dump(function_tree(result, name)), name)

    def test_changed_v1_receiver_is_rejected_before_migration(self):
        v1_source = subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', 'd3d47a4:install-ranch-receiver.py'], text=True)
        legacy_path = ROOT / 'tests/fixtures/install-milk-tea-receiver.py'
        legacy_path.write_text((ROOT / 'install-milk-tea-receiver.py').read_text(encoding='utf-8'), encoding='utf-8')
        self.addCleanup(legacy_path.unlink, missing_ok=True)
        v1_path = ROOT / 'tests/fixtures/install-ranch-receiver-v1-negative.py'
        v1_path.write_text(v1_source, encoding='utf-8')
        self.addCleanup(v1_path.unlink, missing_ok=True)
        v1 = load('ranch_receiver_v1_negative_test', v1_path)
        changed = v1.transform(V5).replace(
            "live_labels.get('qq-farm.maintained-capability') == 'ranch-maintained-v1'",
            "live_labels.get('qq-farm.maintained-capability') in ('ranch-maintained-v1', 'ranch-maintained-v0')", 1)
        with self.assertRaises(RuntimeError):
            ranch.transform(changed)

if __name__ == '__main__':
    unittest.main()
