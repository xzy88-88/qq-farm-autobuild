const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
    const timers = new Map();
    const calls = [];
    const flags = { dog_auto_feed: true };
    const noop = () => {};
    const generic = new Proxy({}, { get: (_target, key) => key === 'CONFIG' ? {} : noop });
    const overrides = {
        'node:worker_threads': { parentPort: null, workerData: null },
        '../models/store': { getAutomation: () => flags },
        '../services/scheduler': { createScheduler: () => ({
            clear: name => timers.delete(name),
            setTimeoutTask: (name, delay, run) => timers.set(name, { delay, run }),
            setIntervalTask: (name, delay, run) => timers.set(name, { delay, run }),
        }) },
        '../services/automation-lock': { runExclusiveAutomationTask: async (_name, run) => run() },
        '../utils/request-context': { runWithRequestClass: (requestClass, run) => { calls.push(requestClass); return run(); } },
        '../services/pets': { runDogFoodAutomation: guard => { if (guard()) calls.push('dog'); } },
    };
    const box = { exports: {} };
    const source = fs.readFileSync(path.join(__dirname, '../dist/core/worker.js'), 'utf8');
    vm.runInNewContext(`${source}
      module.exports = {
        start: typeof startDogFeedTimer === 'function' ? startDogFeedTimer : () => {},
        login: ready => { loginReady = ready; runtimeGeneration++; },
      };
    `, {
        require: name => overrides[name] || generic,
        module: box,
        exports: box.exports,
        process: { env: {} },
        console,
        Buffer,
        Date,
        setTimeout,
        clearTimeout,
    });
    return { api: box.exports, timers, calls, flags };
}

test('dog food timer starts only for a logged-in account with the switch on', async () => {
    const h = harness();
    h.api.start();
    assert.equal(h.timers.size, 0);
    h.api.login(true);
    h.api.start();
    assert.equal(h.timers.get('dog_feed_interval')?.delay, 60000);
    await h.timers.get('dog_feed_initial').run();
    assert.deepEqual(h.calls, ['background', 'dog']);
    h.flags.dog_auto_feed = false;
    h.api.start();
    assert.equal(h.timers.size, 0);
});

test('an old dog food callback cannot feed after the login generation changes', async () => {
    const h = harness();
    h.api.login(true);
    h.api.start();
    const run = h.timers.get('dog_feed_initial')?.run;
    h.api.login(false);
    h.api.login(true);
    await run();
    assert.deepEqual(h.calls, []);
});
