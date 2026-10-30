import copy
import hashlib
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'network_recovery.py'
SPEC = importlib.util.spec_from_file_location('network_recovery', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Gateway:
    """Replace external HTTP/profile boundaries; keep state transitions real."""
    def __init__(self):
        self.record = {'id': '2', 'name': 'existing', 'platform': 'qq',
                       'code': 'original-code', 'running': True}
        self.connected = True
        self.entries = []
        self.profiles = ['bound-qq']
        self.task_status = 'confirmed'
        self.new_code = 'fresh-code'
        self.created = 0
        self.started = []
        self.updates = []
        self.after_code = lambda: None
        self.intent_version = 0
        self.epoch = 'current-panel'
        self.before_recover = lambda: None
        self.before_observe = lambda: None
        self.stopping = False

    def account(self, aid):
        return copy.deepcopy(self.record) if aid == self.record['id'] else None

    def online(self, aid):
        return self.connected

    def events(self, aid):
        return copy.deepcopy(self.entries)

    def profile_hash(self):
        return self.profiles.pop(0) if len(self.profiles) > 1 else self.profiles[0]

    def fence(self, aid):
        return {'epoch': self.epoch, 'version': self.intent_version,
                'codeHash': hashlib.sha256(self.record['code'].encode()).hexdigest()}

    def observe(self, aid):
        self.before_observe()
        return {'fence': self.fence(aid), 'online': bool(self.record['running'] and self.connected and not self.stopping)}

    def recover(self, code, expected):
        self.before_recover()
        if expected != self.fence('2') or self.record['running']:
            raise RuntimeError('RecoveryStateChanged')
        self.intent_version += 1
        self.update_code(self.record, code)
        self.start('2')

    def create_task(self):
        self.created += 1
        return {'task_id': 'opaque-test-task', 'status': self.task_status}

    def get_code(self, task_id):
        assert task_id == 'opaque-test-task'
        self.after_code()
        return self.new_code

    def update_code(self, record, code):
        assert record['id'] == '2'
        self.record['code'] = code
        self.updates.append(record['id'])

    def start(self, aid):
        self.record['running'] = True
        self.started.append(aid)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.io = Gateway()
        self.state = {}
        self.saved = []
        self.config = {'enabled': True, 'account_id': '2', 'profile_hash': 'bound-qq'}

    def tick(self, now=1000):
        return MODULE.step(self.config, self.state, self.io, now,
                           lambda s: self.saved.append(copy.deepcopy(s)))

    def drop(self, **overrides):
        self.tick(1000)
        self.io.record['running'] = False
        self.io.connected = False
        event = {'ts': 1010, 'kind': 'disconnect', 'source': 'heartbeat_timeout',
                 'phase': 'online', 'heartbeat_replies': 69, 'code': 0}
        event.update(overrides)
        self.io.entries = [event]

    def test_online_observation_arms_current_session_without_requesting_auth(self):
        self.assertEqual(self.tick(), 'watching')
        self.assertTrue(self.state['armed'])
        self.assertEqual(self.io.created, 0)
        self.assertEqual(self.state['fence']['version'], 0)

    def test_actual_manual_intent_revision_blocks_even_without_a_log_entry(self):
        self.drop(); self.io.intent_version += 1
        self.tick(1020)
        self.assertEqual(self.io.created, 0)
        self.assertEqual(self.io.started, [])

    def test_manual_stop_immediately_before_atomic_write_wins(self):
        self.drop()
        self.io.before_recover = lambda: setattr(self.io, 'intent_version', 1)
        self.tick(1020)
        self.assertEqual(self.io.updates, [])
        self.assertEqual(self.io.started, [])

    def test_panel_restart_disarms_old_session_without_replaying_disconnect(self):
        self.drop(); self.io.epoch = 'new-panel'
        self.tick(1020)
        self.assertEqual(self.io.created, 0)
        self.assertEqual(self.io.started, [])

    def test_manual_stop_during_arming_cannot_be_adopted_as_an_online_fence(self):
        def stop():
            self.io.intent_version += 1
            self.io.stopping = True  # Existing worker status can remain stale briefly.
        self.io.before_observe = stop
        self.tick(1000)
        self.assertFalse(self.state.get('armed', False))
        self.io.record['running'] = False; self.io.connected = False
        self.io.entries = [{'ts': 1001, 'kind': 'disconnect', 'source': 'heartbeat_timeout',
                            'phase': 'online', 'heartbeat_replies': 10}]
        self.tick(1020)
        self.assertEqual(self.io.created, 0)
        self.assertEqual(self.io.started, [])

    def test_heartbeat_disconnect_gets_fresh_code_and_starts_only_account_two(self):
        self.drop()
        self.assertEqual(self.tick(1020), 'recovered')
        self.assertEqual(self.io.record['code'], 'fresh-code')
        self.assertEqual(self.io.started, ['2'])
        self.assertFalse(self.state['armed'])
        self.assertEqual(self.saved[-1]['attempts'], [1020])

    def test_manual_stop_without_network_event_disarms_without_restarting(self):
        self.drop()
        self.io.entries = []
        self.assertEqual(self.tick(1020), 'manual-or-unknown-stop')
        self.assertFalse(self.state['armed'])
        self.assertEqual(self.io.created, 0)

    def test_kickout_or_later_user_activity_prevents_recovery(self):
        for kind in ['kickout', 'start', 'stop', 'update']:
            with self.subTest(kind=kind):
                self.setUp(); self.drop()
                self.io.entries.append({'ts': 1015, 'kind': kind})
                self.tick(1020)
                self.assertEqual(self.io.started, [])
                self.assertEqual(self.io.created, 0)

    def test_no_prior_online_observation_never_starts_an_idle_account(self):
        self.io.record['running'] = False; self.io.connected = False
        self.assertEqual(self.tick(), 'not-armed')
        self.assertEqual(self.io.created, 0)

    def test_changed_authorization_is_not_overwritten(self):
        self.drop(); self.io.record['code'] = 'user-replacement'
        self.tick(1020)
        self.assertEqual(self.io.record['code'], 'user-replacement')
        self.assertEqual(self.io.created, 0)

    def test_login_rejection_or_incomplete_login_is_not_a_network_recovery(self):
        for values in [{'source': 'ws_error', 'code': 400},
                       {'phase': 'connecting'}, {'heartbeat_replies': 0},
                       {'source': 'kickout'}, {'intentional': True}]:
            with self.subTest(values=values):
                self.setUp(); self.drop(**values); self.tick(1020)
                self.assertEqual(self.io.created, 0)

    def test_wrong_qq_identity_blocks_auth_and_requires_manual_recovery(self):
        self.drop(); self.io.profiles = ['other-qq']
        self.assertEqual(self.tick(1020), 'identity-mismatch')
        self.assertTrue(self.state['blocked'])
        self.assertEqual(self.io.created, 0)

    def test_qr_or_security_confirmation_is_never_automatically_completed(self):
        for status in ['waiting_scan', 'scanned', 'failed', 'expired']:
            with self.subTest(status=status):
                self.setUp(); self.drop(); self.io.task_status = status
                self.assertEqual(self.tick(1020), 'manual-auth-required')
                self.assertEqual(self.io.record['code'], 'original-code')
                self.assertEqual(self.io.started, [])
                self.assertTrue(self.state['blocked'])

    def test_identity_change_during_auth_does_not_update_account(self):
        self.drop(); self.io.profiles = ['bound-qq', 'other-qq']
        self.tick(1020)
        self.assertEqual(self.io.updates, [])
        self.assertEqual(self.io.started, [])

    def test_concurrent_user_code_change_or_start_is_respected(self):
        for mutation in ['code', 'running', 'stop-event']:
            with self.subTest(mutation=mutation):
                self.setUp(); self.drop()
                def change():
                    if mutation == 'code': self.io.record['code'] = 'user-code'
                    if mutation == 'running': self.io.record['running'] = True
                    if mutation == 'stop-event': self.io.entries.append({'ts': 1021, 'kind': 'stop'})
                self.io.after_code = change
                self.tick(1020)
                self.assertEqual(self.io.updates, [])
                self.assertEqual(self.io.started, [])

    def test_three_attempts_per_hour_are_enforced_across_successful_sessions(self):
        self.drop(); self.state['attempts'] = [400, 700, 900]
        self.assertEqual(self.tick(1020), 'rate-limited')
        self.assertEqual(self.io.created, 0)

    def test_ten_minute_cooldown_prevents_auth_request_flood(self):
        self.drop(); self.state['attempts'] = [900]
        self.assertEqual(self.tick(1020), 'cooldown')
        self.assertEqual(self.io.created, 0)

    def test_same_disconnect_is_consumed_before_auth_so_crash_cannot_repeat_it(self):
        self.drop()
        def fail(): raise RuntimeError('auth service unavailable')
        self.io.create_task = fail
        self.tick(1020)
        self.assertEqual(self.state['attempts'], [1020])
        self.assertFalse(self.state['armed'])
        self.assertEqual(self.tick(2000), 'not-armed')

    def test_old_or_empty_code_is_never_submitted_again(self):
        for code in ['', 'original-code']:
            with self.subTest(code=code):
                self.setUp(); self.drop(); self.io.new_code = code
                self.tick(1020)
                self.assertEqual(self.io.updates, [])
                self.assertEqual(self.io.started, [])

    def test_disabled_policy_and_other_accounts_are_untouched(self):
        for config in [{'enabled': False}, {'account_id': '1'}, {'profile_hash': ''}]:
            with self.subTest(config=config):
                self.setUp(); self.config.update(config)
                self.tick(1020)
                self.assertEqual(self.io.created, 0)
                self.assertEqual(self.io.started, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
