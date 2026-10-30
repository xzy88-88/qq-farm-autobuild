"""Bounded recovery for one explicitly enabled QQ account; no old-Code retries."""

import datetime
import hashlib
import json
import os
import pathlib
import runpy
import subprocess
import sys
import time


def fingerprint(value):
    return hashlib.sha256(str(value or '').encode()).hexdigest()


def eligible_event(entries, since):
    relevant = [e for e in entries if float(e.get('ts', 0)) > since]
    if not relevant:
        return None
    last = max(relevant, key=lambda e: float(e['ts']))
    if last.get('kind') != 'disconnect' or last.get('phase') != 'online':
        return None
    if last.get('intentional') or int(last.get('heartbeat_replies', 0)) < 1:
        return None
    if last.get('source') == 'heartbeat_timeout':
        return last
    if last.get('source') == 'ws_close' and int(last.get('code', 0)) == 1006:
        return last
    return None


def step(config, state, io, now, save):
    if (config.get('enabled') is not True or str(config.get('account_id')) != '2'
            or not config.get('profile_hash')):
        return 'disabled'
    aid = '2'
    account = io.account(aid)
    if not account or account.get('platform') != 'qq':
        return 'missing-account'
    if account.get('running'):
        observation = io.observe(aid)
        if (observation.get('online')
                and observation['fence'].get('codeHash') == fingerprint(account.get('code'))):
            state.update(armed=True, code_hash=fingerprint(account.get('code')),
                         last_online=now, blocked=False, fence=observation['fence'])
            save(state)
            return 'watching'
        return 'starting'
    if not state.get('armed'):
        return 'not-armed'
    if state.get('blocked'):
        return 'manual-auth-required'

    def unchanged():
        current = io.account(aid)
        if (not current or current.get('running')
                or fingerprint(current.get('code')) != state.get('code_hash')
                or not state.get('fence') or io.fence(aid) != state['fence']):
            return None
        return current

    account = unchanged()
    event = eligible_event(io.events(aid), state.get('last_online', now))
    if not account or not event:
        state['armed'] = False
        save(state)
        return 'manual-or-unknown-stop'
    attempts = [float(t) for t in state.get('attempts', []) if now - float(t) < 3600]
    if len(attempts) >= 3:
        return 'rate-limited'
    if attempts and now - max(attempts) < 600:
        return 'cooldown'
    if io.profile_hash() != config['profile_hash']:
        state.update(armed=False, blocked=True)
        save(state)
        return 'identity-mismatch'

    # Consume the event before any auth request; a crash or HTTP failure must
    # never re-run the same session recovery on every timer tick.
    state.update(armed=False, attempts=attempts + [now], last_event=event['ts'])
    save(state)
    try:
        task = io.create_task()
        if task.get('status') != 'confirmed':
            state['blocked'] = True
            save(state)
            return 'manual-auth-required'
        code = str(io.get_code(task['task_id']) or '').strip()
        if not code or fingerprint(code) == state.get('code_hash'):
            return 'no-fresh-code'
        if io.profile_hash() != config['profile_hash']:
            state['blocked'] = True
            save(state)
            return 'identity-mismatch'
        account = unchanged()
        latest = eligible_event(io.events(aid), state.get('last_online', now))
        if not account or latest != event:
            return 'user-state-changed'
        # The panel validates this online-session fence, updates Code and starts
        # synchronously in ONE request. Extra client reads cannot close a race.
        io.recover(code, state['fence'])
        return 'recovered'
    except Exception:
        # Errors can contain URLs or tokens; report a fixed reason only.
        return 'recovery-failed'


def atomic_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + '.new')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class Panel:
    def __init__(self):
        sys.path.insert(0, '/opt/qq-farm-autoupdate')
        self.updater = runpy.run_path('/opt/qq-farm-autoupdate/updater.py', run_name='network_recovery_adapter')
        self.token = self.updater['admin_token']()
        inspect = json.loads(subprocess.check_output(['docker', 'inspect', 'qq-farm-bot'], text=True, timeout=10))[0]
        self.log = pathlib.Path(next(m['Source'] for m in inspect['Mounts'] if m.get('Name') == 'qq-farm-logs')) / 'combined.log'

    def request(self, path, aid=None, body=None):
        if body is None:
            return self.updater['admin_request'](path, self.token, aid)
        import urllib.request
        request = urllib.request.Request('http://127.0.0.1:3007' + path,
            data=json.dumps(body).encode(), method='POST',
            headers={'Content-Type': 'application/json', 'x-admin-token': self.token})
        with urllib.request.urlopen(request, timeout=125) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise RuntimeError('panel request failed')
        return result

    def account(self, aid):
        return next((a for a in self.request('/api/accounts')['data']['accounts']
                     if str(a.get('id')) == aid), None)

    def online(self, aid):
        data = self.request('/api/status', aid)['data']
        return bool((data.get('connection') or {}).get('connected'))

    def fence(self, aid):
        return self.observe(aid)['fence']

    def observe(self, aid):
        return self.request('/api/accounts/' + aid + '/network-recovery-state')['data']

    def events(self, aid):
        with self.log.open('rb') as handle:
            handle.seek(max(0, self.log.stat().st_size - 4_000_000))
            lines = handle.read().decode('utf-8', 'replace').splitlines()
        events = []
        for line in lines:
            try:
                item = json.loads(line)
                if str(item.get('accountId')) != aid:
                    continue
                message = item.get('message', '')
                kind = None
                if item.get('source') and item.get('phase'):
                    kind = 'disconnect'
                elif '被踢下线' in message:
                    kind = 'kickout'
                elif '正在启动账号:' in message:
                    kind = 'start'
                elif item.get('action') in ('stop', 'update', 'delete'):
                    kind = item['action']
                if not kind:
                    continue
                stamp = datetime.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')).timestamp()
                diagnostics = item.get('diagnostics') or {}
                events.append({'ts': stamp, 'kind': kind, 'source': item.get('source'),
                    'phase': item.get('phase'), 'code': item.get('disconnectCode', 0),
                    'heartbeat_replies': (diagnostics.get('heartbeat') or {}).get('replies', 0)})
            except (ValueError, TypeError, KeyError):
                continue
        return events

    def profile_hash(self):
        # This is a read-only query; never requests QR login or logout in NapCat.
        javascript = """import 'dotenv/config';
import {createHash} from 'node:crypto';
import {getWebUiLoginProfile} from './napcat-profile.js';
try { const p=await getWebUiLoginProfile();
console.log(JSON.stringify({hash:p.uin?createHash('sha256').update(String(p.uin)).digest('hex'):''}));
} catch { console.log(JSON.stringify({hash:''})); }"""
        output = subprocess.check_output(['node', '--input-type=module', '-e', javascript],
            cwd='/opt/qq-miniapp-auth', text=True, timeout=30)
        return json.loads(output.strip().splitlines()[-1]).get('hash', '')

    def create_task(self):
        return self.request('/api/qq-login/tasks', body={})['data']

    def get_code(self, task_id):
        return self.request('/api/qq-login/tasks/' + task_id + '/code', body={})['data']['code']

    def recover(self, code, expected):
        self.request('/api/accounts/2/recover-network', body={'expected': expected, 'code': code})


def main():
    import fcntl
    root = pathlib.Path('/opt/qq-farm-autoupdate')
    with open('/run/qq-farm-deploy.lock', 'a') as deployment, open('/run/qq-farm-network-recovery.lock', 'a') as own:
        try:
            fcntl.flock(deployment, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(own, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('network-recovery: deployment-or-recovery-active')
            return
        if (root / 'transaction.json').exists() or pathlib.Path('/run/qq-farm-autoupdate-deploy.pause').exists():
            print('network-recovery: deployment-paused')
            return
        config = json.loads((root / 'network-recovery-config.json').read_text())
        path = root / 'network-recovery-state.json'
        state = json.loads(path.read_text()) if path.exists() else {}
        result = step(config, state, Panel(), time.time(), lambda s: atomic_json(path, s))
        print('network-recovery:', result, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('network-recovery: check-failed; no blind restart', flush=True)
        sys.exit(1)
