import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('receiver', ROOT / 'install-milk-tea-receiver.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
BASE = (ROOT / 'tests/fixtures/updater-base.py').read_text(encoding='utf-8')


def function(source, name, namespace):
    node = next(v for v in ast.parse(source).body if isinstance(v, ast.FunctionDef) and v.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<receiver-test>', 'exec'), namespace)
    return namespace[name]


def previous_receiver():
    source = BASE
    for before, after in receiver.replacements_for_base():
        source = source.replace(before, after.replace('milk-tea-auto-v2', 'milk-tea-auto-v1'), 1)
    source = source.replace(r'[0-9a-f]{40}\.tar', r'[0-9a-f]{40}(?:-milk-tea-auto-v1)?\.tar')
    return source.replace(r'qq-farm-bot:auto-[0-9a-f]{12}', r'qq-farm-bot:auto-[0-9a-f]{12}(?:-milk-tea-auto-v1)?')


class ReceiverTests(unittest.TestCase):
    def test_base_and_v1_migrate_to_same_v2_source_and_preserve_login_hook(self):
        current = receiver.transform(BASE)
        previous = previous_receiver()
        self.assertEqual(receiver.transform(previous), current)
        self.assertEqual(receiver.transform(current), current)
        self.assertIn('from login_compat import prepare', current)
        self.assertNotIn('milk-tea-auto-v1', current)

    def test_missing_login_compatibility_is_rejected(self):
        for source in [BASE, receiver.transform(BASE)]:
            with self.assertRaisesRegex(RuntimeError, 'LOGIN_FAILED'):
                receiver.transform(source.replace('from login_compat import prepare', ''))

    def test_unexpected_v1_or_base_structure_is_rejected(self):
        previous = previous_receiver()
        for source in [BASE.replace('def build(revision):', 'def changed_build(revision):'),
                       previous.replace('    check_milk_automation(tag)\n', ''),
                       receiver.transform(BASE).replace('    check_milk_automation(tag)\n', '')]:
            with self.assertRaises(RuntimeError):
                receiver.transform(source)

    def test_install_backs_up_original_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updater = root / 'updater.py'
            previous = previous_receiver()
            updater.write_text(previous, encoding='utf-8')
            result = receiver.install(updater, root / 'backups')
            self.assertEqual(result['status'], 'installed')
            self.assertEqual((Path(result['backup']) / 'updater.py').read_text(encoding='utf-8'), previous)
            self.assertEqual(receiver.install(updater, root / 'backups')['status'], 'already_installed')

    def test_candidate_image_requires_v2_label_before_smoke_test(self):
        for version in ['milk-tea-auto-v1', 'milk-tea-auto-v2']:
            run = Mock(return_value=json.dumps([{'Config': {'Labels': {'qq-farm.milk-tea-automation': version}}}]))
            check = function(receiver.transform(BASE), 'check_milk_automation', {'json': json, 'run': run})
            if version.endswith('v1'):
                with self.assertRaisesRegex(RuntimeError, 'capability missing'):
                    check('candidate')
                self.assertEqual(run.call_count, 1)
            else:
                check('candidate')
                self.assertEqual(run.call_count, 2)
                self.assertIn('--network=none', run.call_args.args[0])

    def test_same_upstream_v1_is_not_skipped_as_up_to_date(self):
        source = receiver.transform(BASE)
        main = next(v for v in ast.parse(source).body if isinstance(v, ast.FunctionDef) and v.name == 'main')
        condition = next(v.test for v in ast.walk(main) if isinstance(v, ast.If)
                         and ast.unparse(v.test).startswith('revision == deployed'))
        expression = compile(ast.Expression(condition), '<skip-condition>', 'eval')
        args = type('Args', (), {'build_check': False})()
        for version, skip in [('milk-tea-auto-v1', False), ('milk-tea-auto-v2', True)]:
            self.assertEqual(eval(expression, {'revision': 'a' * 40, 'deployed': 'a' * 40, 'args': args,
                                               'live_labels': {'qq-farm.milk-tea-automation': version}}), skip)

    def test_build_queries_v2_release_and_rejects_v1_manifest(self):
        import re
        revision = 'a' * 40
        prefix = 'https://github.com/owner/repo/releases/download/upstream-' + revision + '-milk-tea-auto-v2/'
        release = {'tag_name': 'upstream-' + revision + '-milk-tea-auto-v2', 'assets': [
            {'name': name, 'browser_download_url': prefix + name, 'size': 100}
            for name in ['manifest.json', 'qq-farm-image.tar.gz']]}
        metadata = {'revision': revision, 'image_tag': 'qq-farm-bot:auto-' + revision[:12] + '-milk-tea-auto-v2',
                    'build_capability': 'milk-tea-auto-v1', 'sha256': 'b' * 64, 'size': 100,
                    'compatibility': ['qmsg-v3', 'qq-login-confirmed-without-qr', 'milk-tea-auto-v2']}
        github_json = Mock(side_effect=[release, metadata])
        build = function(receiver.transform(BASE), 'build', {'BUILD_REPOSITORY': 'owner/repo',
                                                            'github_json': github_json, 're': re})
        with self.assertRaisesRegex(RuntimeError, 'compatibility metadata'):
            build(revision)
        self.assertTrue(github_json.call_args_list[0].args[0].endswith('-milk-tea-auto-v2'))

    def test_previous_capability_failure_does_not_block_v2_and_new_failures_record_capability(self):
        source = receiver.transform(previous_receiver())
        main = next(v for v in ast.parse(source).body if isinstance(v, ast.FunctionDef) and v.name == 'main')
        gate = next(v.test for v in ast.walk(main) if isinstance(v, ast.If)
                    and ast.unparse(v.test).startswith("state.get('failed_revision') == revision"))
        args = type('Args', (), {'build_check': False, 'retry': False})()
        expression = compile(ast.Expression(gate), '<failure-condition>', 'eval')
        for capability, skip in [(None, False), ('milk-tea-auto-v1', False), ('milk-tea-auto-v2', True)]:
            state = {'failed_revision': 'a' * 40, 'failed_capability': capability}
            self.assertEqual(eval(expression, {'revision': 'a' * 40, 'state': state, 'args': args}), skip)
        failure = next(v for v in ast.walk(main) if isinstance(v, ast.If)
                       and ast.unparse(v.test) == 'deploy_started and (not args.build_check)')
        previous = {}
        exec(compile(ast.Module(body=failure.body, type_ignores=[]), '<failure-write>', 'exec'),
             {'previous': previous, 'revision': 'a' * 40})
        self.assertEqual(previous, {'failed_revision': 'a' * 40, 'failed_capability': 'milk-tea-auto-v2'})


if __name__ == '__main__':
    unittest.main()
