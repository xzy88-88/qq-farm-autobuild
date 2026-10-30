# Bounded QQ Farm network recovery

`network_recovery.py` is an opt-in server maintenance companion to the v5
application. It only handles explicitly enabled account `2` and requires the
authenticated conditional recovery endpoints shipped by v5. It never retries
an old Code or starts an account that was not first observed online.

The private server configuration binds a SHA-256 fingerprint of the already
verified QQ login. Check that profile before and after obtaining a fresh Code.
If login confirmation is needed or the QQ identity changed, stop and require
manual action. Never call the QQ logout or task-cancel endpoints.

Observe online status together with the panel's process epoch, manual-intent
revision and credential fingerprint. The final conditional operation compares
that original observation and updates/starts synchronously. This preserves a
manual Stop even when the worker is already offline and closes concurrent
credential-update/start races. A panel process restart invalidates old intent.

Each disconnect is consumed before requesting authorization. At most three
recoveries are attempted per rolling hour, with ten minutes between attempts.
An authorization-request failure consumes that event rather than polling the
same credential indefinitely. The next genuinely online session rearms the
watcher. The existing retired-account guard and account `1` remain unchanged.

Use the existing deployment lock and pause/transaction markers. Configuration
and state belong to `/opt/qq-farm-autoupdate/`, mode `0600`; do not publish them.
Back up the companion and unit files before replacing them. Installation must
first confirm v5 capability, account `2` online and the original QQ identity;
initial watcher execution must only report `watching`, without game writes.

Validation:

```text
python -m unittest discover -s maintenance/tests -v
python -m unittest discover -s tests -v
```

Recovery mitigates loss of game replies; it does not establish the underlying
cause of a silent gateway connection. Do not deliberately disconnect a real
account solely to demonstrate recovery.
