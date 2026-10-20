const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
    const timers = new Map();
    const calls = [];
    const flags = { milk_tea_auto_craft: true };
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
        '../services/milk-tea': { runMilkTeaAutomation: guard => { if (guard()) calls.push('milk'); } },
    };
    const box = { exports: {} };
    const source = fs.readFileSync(path.join(__dirname, '../dist/core/worker.js'), 'utf8');
    vm.runInNewContext(source + `
      module.exports = {
        start: typeof startMilkTeaTimer === 'function' ? startMilkTeaTimer : () => {},
        login: ready => { loginReady = ready; runtimeGeneration++; },
      };
    `, { require: name => overrides[name] || generic, module: box, exports: box.exports,
        process: { env: {} }, console, Buffer, Date, setTimeout, clearTimeout });
    return { api: box.exports, timers, calls, flags };
}

test('milk tea timer starts only for logged-in enabled accounts and uses the background request class', async () => {
    const h = harness();
    h.api.start();
    assert.equal(h.timers.size, 0);
    h.api.login(true); h.api.start();
    assert.equal(h.timers.get('milk_tea_interval')?.delay, 60000);
    await h.timers.get('milk_tea_initial').run();
    assert.deepEqual(h.calls, ['background', 'milk']);
    h.flags.milk_tea_auto_craft = false; h.api.start();
    assert.equal(h.timers.size, 0);
});

test('milk tea timer also starts when only friend hiring is enabled', async () => {
    const h = harness();
    h.flags.milk_tea_auto_craft = false;
    h.flags.milk_tea_auto_hire = true;
    h.api.login(true);
    h.api.start();
    assert.equal(h.timers.get('milk_tea_interval')?.delay, 60000);
    h.flags.milk_tea_auto_hire = false;
    h.api.start();
    assert.equal(h.timers.size, 0);
});

test('a callback from an old login generation cannot run milk tea actions', async () => {
    const h = harness();
    h.api.login(true); h.api.start();
    const run = h.timers.get('milk_tea_initial')?.run;
    assert.equal(typeof run, 'function');
    h.api.login(false); h.api.login(true);
    await run();
    assert.deepEqual(h.calls, []);
});
