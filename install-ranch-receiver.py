"""Migrate the verified existing receiver to maintained ranch releases."""
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import time

CAPABILITY = 'ranch-maintained-v2'
MARKER = '# maintained ranch-maintained-v2 receiver'
LABELS = {'qq-farm.maintained-capability': CAPABILITY,
          'qq-farm.friend-relation-guard': 'not-friend-v1',
          'qq-farm.network-recovery': 'network-recovery-v1'}
SMOKE = '''const r=require("./dist/services/ranch"); const f=require("./dist/services/network-recovery-fence"); const a=require("./dist/config/ranch-automation").RANCH_AUTOMATION_DEFAULTS; if(typeof r.getRanchState!=="function" || typeof r.operateRanch!=="function" || typeof f.createRecoveryFence!=="function" || a.ranch_buy || a.ranch_grass_buy || a.ranch_upgrade) throw Error("invalid maintained ranch capability")'''
CHECK = '''def check_maintained_ranch(tag):
    labels = json.loads(run(['docker', 'image', 'inspect', tag]))[0]['Config'].get('Labels', {})
    required = %r
    if any(labels.get(key) != value for key, value in required.items()):
        raise RuntimeError('Maintained ranch capability missing; existing deployment preserved')
    script = %r
    run(['docker', 'run', '--rm', '--network=none', '--memory=256m', '--tmpfs', '/app/core/data:rw,size=16m', '--entrypoint', 'node', tag, '-e', script])


''' % (LABELS, SMOKE)
PROTECTED = ('deployment_lock', 'snapshot_data', 'restore_data', 'recovery_locked', 'recovery', 'deploy_locked', 'deploy')

def legacy_receiver():
    here = pathlib.Path(__file__).resolve().parent
    path = here / 'install-milk-tea-receiver.py'
    if not path.exists():
        path = here / 'install-milk-tea-v5.py'
    spec = importlib.util.spec_from_file_location('verified_legacy_receiver', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate(source):
    ast.parse(source)
    if (source.count(MARKER) != 1 or source.count(CHECK) != 1
            or 'from login_compat import prepare' not in source
            or 'tag = prepare(tag, revision)' not in source
            or 'milk-tea-auto-v5' in source
            or "live_labels.get('qq-farm.maintained-capability') == 'ranch-maintained-v2'" not in source):
        raise RuntimeError('Maintained ranch receiver changed; review required')

def transform(source):
    if MARKER in source:
        validate(source)
        return source
    legacy = legacy_receiver()
    verified = legacy.transform(source)
    before = ast.parse(verified)
    if verified.count(legacy.CHECK) != 1:
        raise RuntimeError('Legacy capability check changed')
    result = verified.replace(legacy.CHECK, CHECK, 1)
    result = result.replace('milk-tea-auto-v5', CAPABILITY)
    result = result.replace('check_milk_automation(tag)', 'check_maintained_ranch(tag)')
    old_key = "live_labels.get('qq-farm.milk-tea-automation')"
    if result.count(old_key) != 1:
        raise RuntimeError('Legacy skip capability changed')
    result = result.replace(old_key, "live_labels.get('qq-farm.maintained-capability')", 1)
    after = ast.parse(result)
    for name in PROTECTED:
        old = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == name)
        new = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == name)
        if ast.dump(old) != ast.dump(new):
            raise RuntimeError('Protected transaction function changed: ' + name)
    validate(result)
    return result

def install(updater, backup_root):
    updater = pathlib.Path(updater)
    original = updater.read_text(encoding='utf-8')
    patched = transform(original)
    if patched == original:
        return {'status': 'already_installed', 'capability': CAPABILITY}
    backup = pathlib.Path(backup_root) / ('ranch-receiver-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copy2(updater, backup / 'updater.py')
    temporary = updater.with_name('updater.ranch.tmp')
    temporary.write_text(patched, encoding='utf-8')
    temporary.chmod(updater.stat().st_mode & 0o777)
    os.replace(temporary, updater)
    return {'status': 'installed', 'capability': CAPABILITY, 'backup': str(backup),
            'before_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'after_sha256': hashlib.sha256(patched.encode()).hexdigest()}

if __name__ == '__main__':
    import fcntl
    with open('/opt/qq-farm-autoupdate/update.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(install('/opt/qq-farm-autoupdate/updater.py', '/opt/backups/qq-farm-bot')))
