from login_compat import prepare
#!/usr/bin/env python3
"""Bounded, transactional GitHub updates for the existing QQ Farm deployment."""
import argparse, ast, contextlib, fcntl, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tarfile, time, urllib.request

ROOT = pathlib.Path('/opt/qq-farm-autoupdate')
APP = pathlib.Path('/opt/qq-farm-bot')
STATE = ROOT / 'state.json'
TX = ROOT / 'transaction.json'
PAUSE = pathlib.Path('/run/qq-farm-autoupdate-deploy.pause')
CONTAINER = 'qq-farm-bot'
BUILD_CONTAINER = 'qq-farm-autobuild'
REMOTE = 'https://github.com/liyangpengs/qq-farm-bot.git'
DEPLOY_LOCK = None

@contextlib.contextmanager
def deployment_lock():
    global DEPLOY_LOCK
    if DEPLOY_LOCK is not None:
        yield
        return
    with open('/run/qq-farm-deploy.lock', 'w') as lock:
        deadline = time.monotonic() + 60
        while True:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic() > deadline: raise RuntimeError('Farm guard busy; update deferred')
                time.sleep(1)
        DEPLOY_LOCK = lock
        try: yield
        finally: DEPLOY_LOCK = None

def log(s):
    print(time.strftime('%Y-%m-%d %H:%M:%S ') + s, flush=True)

def run(args, timeout=120, capture=True, cwd=None):
    p = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, timeout=timeout)
    if p.returncode:
        # Do not dump commands or container output that might include settings.
        raise RuntimeError('Command failed: ' + str(args[0]) + ' exit ' + str(p.returncode))
    return p.stdout.strip() if capture else ''

def save(path, obj):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    os.chmod(temp, 0o600)
    os.replace(temp, path)

def read(path):
    return json.loads(path.read_text()) if path.exists() else {}

def inspect():
    return json.loads(run(['docker', 'inspect', CONTAINER]))[0]

def health(timeout=100):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            i = inspect()
            with urllib.request.urlopen('http://127.0.0.1:3007/api/game-version', timeout=5) as r:
                data = json.load(r)
            if i['State']['Running'] and i['State'].get('Health', {}).get('Status') == 'healthy' and data.get('ok'):
                with urllib.request.urlopen('http://127.0.0.1:3007/', timeout=5) as r:
                    if r.status == 200:
                        return True
        except Exception:
            pass
        time.sleep(2)
    return False

def compose(*args):
    return run(['docker', 'compose', 'up', '-d', '--no-build', '--force-recreate', CONTAINER], cwd=APP)

def snapshot_data(folder, info):
    for mount in info['Mounts']:
        if mount['Destination'] == '/app/core/data':
            with tarfile.open(folder / 'data.tar.gz', 'w:gz') as tf:
                tf.add(mount['Source'], arcname='data')

def restore_data(folder, info):
    source = pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination'] == '/app/core/data'))
    # The logs mount is a separate live volume and is never purged.
    for item in source.iterdir():
        if item.name == 'logs':
            continue
        if item.is_dir(): shutil.rmtree(item)
        else: item.unlink()
    with tarfile.open(folder / 'data.tar.gz') as tf:
        for member in tf.getmembers():
            if member.name == 'data': continue
            member.name = member.name.removeprefix('data/')
            if member.name == 'logs' or member.name.startswith('logs/'): continue
            tf.extract(member, source, filter='data')

def recovery_locked():
    tx = read(TX)
    if not tx:
        return
    if tx.get('phase') == 'committed':
        TX.unlink(missing_ok=True)
        PAUSE.unlink(missing_ok=True)
        return
    log('Restoring previous deployment after interrupted or failed update')
    run(['docker', 'stop', '-t', '20', CONTAINER], timeout=40)
    if tx.get('data_ready'):
        restore_data(pathlib.Path(tx['backup']), tx['container'])
    run(['docker', 'image', 'tag', tx['old_image'], 'qq-farm-bot:latest'])
    compose()
    if not health(): raise RuntimeError('Rollback health check failed; guard remains paused')
    TX.unlink(missing_ok=True)
    PAUSE.unlink(missing_ok=True)
    restore_running(tx.get('running_accounts', []))
    log('Previous version restored successfully')

def recovery():
    if not TX.exists(): return
    with deployment_lock(): recovery_locked()

def is_user_logging_in():
    with urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=5) as r:
        return bool(json.load(r).get('workflowBusy'))

def admin_request(path, token=None, account=None, body=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['x-admin-token'] = token
    if account: headers['x-account-id'] = str(account)
    req = urllib.request.Request('http://127.0.0.1:3007' + path, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)

def admin_token():
    config = {}
    tree = ast.parse(pathlib.Path('/root/qq-farm-guard.py').read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and len(n.value.args) > 1:
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in ('ADMIN_USER', 'ADMIN_PASS'):
                    config[t.id] = os.environ.get(t.id) or ast.literal_eval(n.value.args[1])
    if len(config) != 2: raise RuntimeError('Existing admin authentication configuration unavailable')
    return admin_request('/api/login', body={'username': config['ADMIN_USER'], 'password': config['ADMIN_PASS']})['data']['token']

def restore_running(ids):
    if not ids: return
    token = admin_token()
    for account in ids:
        try: admin_request('/api/accounts/' + str(account) + '/start', token, body={})
        except Exception: log('Account restart needs a valid game login Code: ' + str(account))

# Inserted into the server updater. All compilation happens on GitHub.
BUILD_REPOSITORY = 'xzy88-88/qq-farm-autobuild'

def github_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'qq-farm-autoupdate', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read(65536))

def cleanup_downloads(current):
    downloads = ROOT / 'downloads'
    if not downloads.exists(): return
    archives = sorted((p for p in downloads.iterdir()
                       if re.fullmatch(r'[0-9a-f]{40}\.tar\.gz', p.name) and p.is_file()
                       and not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = {current}
    for path in archives:
        if len(keep) < 2: keep.add(path.name)
    for path in archives:
        if path.name not in keep: path.unlink()
    for path in downloads.iterdir():
        if (re.fullmatch(r'[0-9a-f]{40}\.tar\.part', path.name) and path.is_file()
                and not path.is_symlink() and time.time() - path.stat().st_mtime > 86400):
            path.unlink()

def build(revision):
    import urllib.error
    url = 'https://api.github.com/repos/' + BUILD_REPOSITORY + '/releases/tags/upstream-' + revision
    try:
        release = github_json(url)
    except urllib.error.HTTPError as error:
        if error.code == 404: return None
        raise
    assets = {a['name']: a for a in release.get('assets', [])}
    if release.get('draft') or release.get('prerelease') or release.get('tag_name') != 'upstream-' + revision:
        raise RuntimeError('Cloud build release metadata is invalid')
    prefix = 'https://github.com/' + BUILD_REPOSITORY + '/releases/download/upstream-' + revision + '/'
    for name in ('manifest.json', 'qq-farm-image.tar.gz'):
        if name not in assets or assets[name]['browser_download_url'] != prefix + name:
            raise RuntimeError('Cloud build release asset is invalid: ' + name)
    metadata = github_json(assets['manifest.json']['browser_download_url'])
    tag = 'qq-farm-bot:auto-' + revision[:12]
    checksum = str(metadata.get('sha256', ''))
    required = {'qmsg-v3', 'qq-login-confirmed-without-qr'}
    if (metadata.get('revision') != revision or metadata.get('image_tag') != tag
            or not re.fullmatch(r'[0-9a-f]{64}', checksum)
            or not required.issubset(set(metadata.get('compatibility', [])))):
        raise RuntimeError('Cloud build checksum or compatibility metadata is invalid')
    size = int(metadata.get('size', 0))
    if size <= 0 or size > 1024**3 or assets['qq-farm-image.tar.gz'].get('size') != size:
        raise RuntimeError('Cloud build archive size is invalid')
    downloads = ROOT / 'downloads'; downloads.mkdir(exist_ok=True)
    archive = downloads / (revision + '.tar.gz')
    def digest(path):
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
        return h.hexdigest()
    if not archive.exists() or archive.stat().st_size != size or digest(archive) != checksum:
        part = archive.with_suffix('.part')
        if part.exists() and part.stat().st_size >= size:
            if part.stat().st_size == size and digest(part) == checksum:
                os.replace(part, archive)
            else:
                part.unlink()
        log('Downloading the verified GitHub build for ' + revision[:12])
        if not archive.exists() or archive.stat().st_size != size or digest(archive) != checksum:
            run(['curl', '--fail', '--location', '--silent', '--show-error', '--connect-timeout', '20',
                 '--max-time', '1200', '--continue-at', '-', '--output', str(part),
                 assets['qq-farm-image.tar.gz']['browser_download_url']], timeout=1250)
            if part.stat().st_size != size or digest(part) != checksum:
                part.unlink(missing_ok=True)
                raise RuntimeError('Downloaded archive checksum failed; existing version preserved')
            os.replace(part, archive)
    # Docker load must not introduce an unexpected mutable 'latest' tag.
    with tarfile.open(archive, 'r:gz') as tf:
        member = tf.getmember('manifest.json')
        if member.size > 65536: raise RuntimeError('Docker archive manifest is too large')
        manifest = json.load(tf.extractfile(member))
        if len(manifest) != 1 or manifest[0].get('RepoTags') != [tag]:
            raise RuntimeError('Unexpected Docker archive image tags')
    run(['docker', 'load', '--input', str(archive)], timeout=600)
    image = json.loads(run(['docker', 'image', 'inspect', tag]))[0]
    if image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') != revision:
        raise RuntimeError('Loaded image revision does not match upstream')
    run(['docker', 'run', '--rm', '--network=none', '--memory=256m', '--entrypoint=node', tag,
         '-e', 'require("./dist/services/qq-login/service"); require("./dist/services/push")'])
    canary(tag)
    cleanup_downloads(archive.name)
    return tag


def cleanup_artifacts():
    # Retain two source/build trees and five automatic rollback image tags.
    # Original manual backups and all account data backups are untouched.
    directories = sorted((ROOT / 'releases').iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for folder in directories[2:]:
        if re.fullmatch(r'[0-9a-f]{40}', folder.name) and folder.resolve().parent == (ROOT / 'releases').resolve():
            shutil.rmtree(folder)
    tags = run(['docker', 'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}']).splitlines()
    rollbacks = sorted((t for t in tags if t.startswith('qq-farm-bot:rollback-auto-')), reverse=True)
    candidates = [t for t in tags if re.fullmatch(r'qq-farm-bot:auto-[0-9a-f]{12}', t)]
    candidates.sort(key=lambda t: json.loads(run(['docker', 'image', 'inspect', t]))[0]['Created'], reverse=True)
    for tag in rollbacks[5:] + candidates[2:]:
        subprocess.run(['docker', 'image', 'rm', tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def canary(tag):
    name = 'qq-farm-autocanary'
    try:
        run(['docker', 'run', '-d', '--name', name, '--network=none', '--memory=256m',
             '--tmpfs', '/app/core/data:rw,size=16m', tag])
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            info = json.loads(run(['docker', 'inspect', name]))[0]
            if info['State'].get('Health', {}).get('Status') == 'healthy':
                data = json.loads(run(['docker', 'exec', name, 'wget', '-qO-', 'http://127.0.0.1:3007/api/game-version']))
                if data.get('ok'):
                    run(['docker', 'exec', name, 'wget', '-q', '--spider', 'http://127.0.0.1:3007/'])
                    log('Isolated candidate startup and panel checks passed')
                    return
            time.sleep(2)
        raise RuntimeError('Isolated candidate did not become healthy')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def deploy_locked(tag, revision):
    if is_user_logging_in(): raise RuntimeError('Active QR login; update deferred')
    token = admin_token()
    accounts = admin_request('/api/accounts', token)['data']['accounts']
    running = [a['id'] for a in accounts if a.get('running')]
    info = inspect()
    backup = pathlib.Path('/opt/backups/qq-farm-bot/auto-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    shutil.copy2(APP / '.env', backup / 'env-before')
    old_tag = 'qq-farm-bot:rollback-auto-' + time.strftime('%Y%m%d-%H%M%S')
    run(['docker', 'image', 'tag', info['Image'], old_tag])
    tx = {'phase': 'prepared', 'old_image': info['Image'], 'backup': str(backup), 'container': info,
          'running_accounts': running, 'data_ready': False}
    save(TX, tx)
    PAUSE.touch()
    try:
        run(['docker', 'stop', '-t', '20', CONTAINER], timeout=40)
        snapshot_data(backup, info)
        tx['data_ready'] = True; save(TX, tx)
        run(['docker', 'image', 'tag', tag, 'qq-farm-bot:latest'])
        compose()
        if not health(): raise RuntimeError('New version failed health checks')
        # Verify the existing administrator can authenticate after startup.
        admin_token()
        tx['phase'] = 'committed'; save(TX, tx)
        save(STATE, {'status': 'updated', 'revision': revision, 'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                     'backup': str(backup)})
        TX.unlink(); PAUSE.unlink(missing_ok=True)
        restore_running(running)
        log('Updated successfully to ' + revision[:12])
    except BaseException:
        recovery()
        raise

def deploy(tag, revision):
    with deployment_lock(): deploy_locked(tag, revision)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-check', action='store_true', help='Download and verify cloud build without deploying')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--retry', action='store_true', help='Retry a previously failed revision')
    args = parser.parse_args()
    ROOT.mkdir(exist_ok=True)
    with (ROOT / 'update.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: log('Another check is already running'); return
        recovery()
        if args.recover: return
        deploy_started = False
        try:
            if shutil.disk_usage(ROOT).free < 6 * 1024**3: raise RuntimeError('Less than 6 GiB free disk; deferred')
            if is_user_logging_in(): log('QR login in progress; check deferred'); return
            repo = ROOT / 'repo.git'
            if not repo.exists(): run(['git', 'init', '--bare', str(repo)])
            run(['git', '--git-dir', str(repo), 'fetch', '--depth=1', REMOTE, 'master'], timeout=180)
            revision = run(['git', '--git-dir', str(repo), 'rev-parse', 'FETCH_HEAD'])
            deployed = inspect()['Config'].get('Labels', {}).get('org.opencontainers.image.revision', '')
            state = read(STATE)
            if revision == deployed and not args.build_check:
                state.pop('last_error', None)
                state.pop('failed_revision', None)
                state.update(status='up_to_date', revision=revision, checked_at=time.strftime('%Y-%m-%d %H:%M:%S'))
                save(STATE, state); log('Already up to date: ' + revision[:12]); return
            if state.get('failed_revision') == revision and not args.build_check and not args.retry:
                log('This revision previously failed; waiting for a newer commit or manual retry'); return
            if not health(10): raise RuntimeError('Existing application is not healthy; update deferred')
            tag = build(revision)
            if tag is None:
                state.update(status='waiting_for_cloud_build', revision=deployed,
                             pending_revision=revision, checked_at=time.strftime('%Y-%m-%d %H:%M:%S'))
                state.pop('last_error', None)
                save(STATE, state)
                log('GitHub has not published this commit yet; existing version preserved')
                return
            if args.build_check:
                save(ROOT / 'build-check.json', {'revision': revision, 'tag': tag, 'ok': True})
                log('Full build check passed; live deployment unchanged'); return
            deploy_started = True
            deploy(tag, revision)
            cleanup_artifacts()
        except Exception as e:
            previous = read(STATE)
            previous.update(status='failed', last_error=str(e), checked_at=time.strftime('%Y-%m-%d %H:%M:%S'))
            if deploy_started and not args.build_check: previous['failed_revision'] = revision
            save(STATE, previous)
            log('Update not applied: ' + str(e))
            raise

if __name__ == '__main__': main()
