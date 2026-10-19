"""Preserve verified milk-tea-auto-v1 releases with the existing transactional updater."""
import ast
import hashlib
import json
import os
import pathlib
import shutil
import time

CAPABILITY = 'milk-tea-auto-v1'
MARKER = '# maintained milk-tea-auto-v1 receiver'

CHECK = '''def check_milk_automation(tag):
    labels = json.loads(run(['docker', 'image', 'inspect', tag]))[0]['Config'].get('Labels', {})
    if labels.get('qq-farm.milk-tea-automation') != 'milk-tea-auto-v1':
        raise RuntimeError('Milk tea automation capability missing; existing deployment preserved')
    script = 'const m=require("./dist/services/milk-tea");if(typeof m.runMilkTeaAutomation!=="function"||typeof m.getMilkTeaAutomationState!=="function"||m.getMilkTeaAutomationState().autoCraft)throw Error("invalid milk tea automation capability")'
    run(['docker', 'run', '--rm', '--network=none', '--tmpfs', '/app/core/data:rw,size=16m', '--entrypoint', 'node', tag, '-e', script])


'''


def transform(source):
    if MARKER in source:
        ast.parse(source)
        return source
    if 'from login_compat import prepare' not in source:
        raise RuntimeError('Existing LOGIN_FAILED compatibility hook must be present first')

    replacements = [
        ("'/releases/tags/upstream-' + revision", "'/releases/tags/upstream-' + revision + '-milk-tea-auto-v1'"),
        ("release.get('tag_name') != 'upstream-' + revision:", "release.get('tag_name') != 'upstream-' + revision + '-milk-tea-auto-v1':"),
        ("'/releases/download/upstream-' + revision + '/'", "'/releases/download/upstream-' + revision + '-milk-tea-auto-v1/'"),
        ("tag = 'qq-farm-bot:auto-' + revision[:12]", "tag = 'qq-farm-bot:auto-' + revision[:12] + '-milk-tea-auto-v1'"),
        ("required = {'qmsg-v3', 'qq-login-confirmed-without-qr'}", "required = {'qmsg-v3', 'qq-login-confirmed-without-qr', 'milk-tea-auto-v1'}"),
        ("if (metadata.get('revision') != revision or metadata.get('image_tag') != tag", "if (metadata.get('revision') != revision or metadata.get('image_tag') != tag\n            or metadata.get('build_capability') != 'milk-tea-auto-v1'"),
        ("archive = downloads / (revision + '.tar.gz')", "archive = downloads / (revision + '-milk-tea-auto-v1.tar.gz')"),
        ("deployed = inspect()['Config'].get('Labels', {}).get('org.opencontainers.image.revision', '')", "live_labels = inspect()['Config'].get('Labels', {})\n            deployed = live_labels.get('org.opencontainers.image.revision', '')"),
        ("if revision == deployed and not args.build_check:", "if revision == deployed and live_labels.get('qq-farm.milk-tea-automation') == 'milk-tea-auto-v1' and not args.build_check:"),
        ("    canary(tag)\n    cleanup_downloads", "    check_milk_automation(tag)\n    canary(tag)\n    cleanup_downloads"),
        ("def build(revision):", MARKER + '\n' + CHECK + 'def build(revision):'),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError('Updater changed; review required before installing: ' + before[:70])
        source = source.replace(before, after, 1)
    source = source.replace(r'[0-9a-f]{40}\.tar', r'[0-9a-f]{40}(?:-milk-tea-auto-v1)?\.tar')
    source = source.replace(r'qq-farm-bot:auto-[0-9a-f]{12}', r'qq-farm-bot:auto-[0-9a-f]{12}(?:-milk-tea-auto-v1)?')
    ast.parse(source)
    return source


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
