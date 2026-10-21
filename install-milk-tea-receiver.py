"""Preserve verified milk-tea-auto-v2 releases with the existing transactional updater."""
import ast
import hashlib
import json
import os
import pathlib
import shutil
import time

CAPABILITY = 'milk-tea-auto-v2'
MARKER = '# maintained milk-tea-auto-v2 receiver'

CHECK = '''def check_milk_automation(tag):
    labels = json.loads(run(['docker', 'image', 'inspect', tag]))[0]['Config'].get('Labels', {})
    if labels.get('qq-farm.milk-tea-automation') != 'milk-tea-auto-v2':
        raise RuntimeError('Milk tea automation capability missing; existing deployment preserved')
    script = 'const m=require("./dist/services/milk-tea");if(typeof m.runMilkTeaAutomation!=="function"||typeof m.getMilkTeaAutomationState!=="function"||m.getMilkTeaAutomationState().autoCraft)throw Error("invalid milk tea automation capability")'
    run(['docker', 'run', '--rm', '--network=none', '--tmpfs', '/app/core/data:rw,size=16m', '--entrypoint', 'node', tag, '-e', script])


'''


def transform(source):
    if 'from login_compat import prepare' not in source:
        raise RuntimeError('Existing LOGIN_FAILED compatibility hook must be present first')
    if MARKER in source:
        validate_maintained_receiver(source, CAPABILITY)
        return source
    previous = 'milk-tea-auto-v1'
    if '# maintained ' + previous + ' receiver' in source:
        # Only migrate the known v1 receiver, preserving its transactional and login hooks.
        validate_maintained_receiver(source, previous)
        source = source.replace(previous, CAPABILITY)
        source = replace_once(source, replacements_for_failure_identity())
        ast.parse(source)
        return source

    source = replace_once(source, replacements_for_base() + replacements_for_failure_identity())
    source = source.replace(r'[0-9a-f]{40}\.tar', r'[0-9a-f]{40}(?:-milk-tea-auto-v2)?\.tar')
    source = source.replace(r'qq-farm-bot:auto-[0-9a-f]{12}', r'qq-farm-bot:auto-[0-9a-f]{12}(?:-milk-tea-auto-v2)?')
    ast.parse(source)
    return source


def replace_once(source, replacements):
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError('Updater changed; review required before installing: ' + before[:70])
        source = source.replace(before, after, 1)
    return source


def validate_maintained_receiver(source, capability):
    replacements = replacements_for_base()
    if capability == CAPABILITY:
        replacements += replacements_for_failure_identity()
    for fragment in [MARKER, CHECK, *[after for _, after in replacements]]:
        expected = fragment.replace(CAPABILITY, capability)
        if source.count(expected) != 1:
            raise RuntimeError('Existing receiver changed; review required before migration')
    ast.parse(source)


def replacements_for_failure_identity():
    return [
        ("if state.get('failed_revision') == revision and not args.build_check and not args.retry:",
         "if state.get('failed_revision') == revision and state.get('failed_capability') == 'milk-tea-auto-v2' and not args.build_check and not args.retry:"),
        ("if deploy_started and not args.build_check: previous['failed_revision'] = revision",
         "if deploy_started and not args.build_check: previous.update(failed_revision=revision, failed_capability='milk-tea-auto-v2')"),
        ("state.pop('failed_revision', None)",
         "state.pop('failed_revision', None)\n                state.pop('failed_capability', None)"),
    ]


def replacements_for_base():
    return [
        ("'/releases/tags/upstream-' + revision", "'/releases/tags/upstream-' + revision + '-milk-tea-auto-v2'"),
        ("release.get('tag_name') != 'upstream-' + revision:", "release.get('tag_name') != 'upstream-' + revision + '-milk-tea-auto-v2':"),
        ("'/releases/download/upstream-' + revision + '/'", "'/releases/download/upstream-' + revision + '-milk-tea-auto-v2/'"),
        ("tag = 'qq-farm-bot:auto-' + revision[:12]", "tag = 'qq-farm-bot:auto-' + revision[:12] + '-milk-tea-auto-v2'"),
        ("required = {'qmsg-v3', 'qq-login-confirmed-without-qr'}", "required = {'qmsg-v3', 'qq-login-confirmed-without-qr', 'milk-tea-auto-v2'}"),
        ("if (metadata.get('revision') != revision or metadata.get('image_tag') != tag", "if (metadata.get('revision') != revision or metadata.get('image_tag') != tag\n            or metadata.get('build_capability') != 'milk-tea-auto-v2'"),
        ("archive = downloads / (revision + '.tar.gz')", "archive = downloads / (revision + '-milk-tea-auto-v2.tar.gz')"),
        ("deployed = inspect()['Config'].get('Labels', {}).get('org.opencontainers.image.revision', '')", "live_labels = inspect()['Config'].get('Labels', {})\n            deployed = live_labels.get('org.opencontainers.image.revision', '')"),
        ("if revision == deployed and not args.build_check:", "if revision == deployed and live_labels.get('qq-farm.milk-tea-automation') == 'milk-tea-auto-v2' and not args.build_check:"),
        ("    canary(tag)\n    cleanup_downloads", "    check_milk_automation(tag)\n    canary(tag)\n    cleanup_downloads"),
        ("def build(revision):", MARKER + '\n' + CHECK + 'def build(revision):'),
    ]


def install(updater, backup_root):
    updater = pathlib.Path(updater)
    original = updater.read_text(encoding='utf-8')
    patched = transform(original)
    if patched == original:
        return {'status': 'already_installed', 'capability': CAPABILITY}
    backup = pathlib.Path(backup_root) / ('milk-tea-receiver-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copy2(updater, backup / 'updater.py')
    temporary = updater.with_name('updater.milk-tea-auto.tmp')
    try:
        temporary.write_text(patched, encoding='utf-8')
        temporary.chmod(updater.stat().st_mode & 0o777)
        os.replace(temporary, updater)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'status': 'installed', 'capability': CAPABILITY, 'backup': str(backup),
            'before_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'after_sha256': hashlib.sha256(patched.encode()).hexdigest()}


if __name__ == '__main__':
    import fcntl
    with open('/opt/qq-farm-autoupdate/update.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(install('/opt/qq-farm-autoupdate/updater.py', '/opt/backups/qq-farm-bot')))
