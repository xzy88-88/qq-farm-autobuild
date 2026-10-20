const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');

function harness({ pauseEncoding = false } = {}) {
    const file = path.resolve(__dirname, '../dist/utils/network.js');
    const realRequire = createRequire(file);
    const priority = realRequire('./request-priority');
    let dispatch = false;
    let finishEncoding;
    const encoding = pauseEncoding ? new Promise(resolve => finishEncoding = resolve) : Promise.resolve();
    const packets = [];
    const box = { exports: {} };
    const overrides = {
        ws: { OPEN: 1 },
        '../services/scheduler': { createScheduler: () => ({ clear() {}, clearAll() {}, setTimeoutTask() {} }) },
        './request-priority': { ...priority, selectDispatchIndex: (...args) => dispatch ? priority.selectDispatchIndex(...args) : -1 },
    };
    vm.runInNewContext(fs.readFileSync(file, 'utf8') + `
        ws = { readyState: 1, send: packet => packets.push(packet) };
        currentConnection = { socket: ws, phase: 'online', finalized: false };
        encodeMsg = async () => { await encoding; return Buffer.from('fixture'); };
        module.exports.flush = drainRequestQueue;
    `, { require: name => overrides[name] || realRequire(name), module: box, exports: box.exports,
        Buffer, console, process, Date, packets, encoding });
    return { api: box.exports, packets, flush: () => { dispatch = true; box.exports.flush(); }, finishEncoding };
}

test('queued background writes recheck their guard before sending after a switch is disabled', async () => {
    const h = harness();
    let enabled = true;
    const pending = h.api.sendMsgAsync('fixture.Service', 'Craft', Buffer.alloc(0), { expectReply: false, requestClass: 'background', beforeSend: () => enabled });
    enabled = false;
    h.flush();
    await assert.rejects(pending, /取消/);
    assert.equal(h.packets.length, 0);
});

test('a switch disabled during asynchronous encoding still prevents the socket write', async () => {
    const h = harness({ pauseEncoding: true });
    let enabled = true;
    const pending = h.api.sendMsgAsync('fixture.Service', 'Craft', Buffer.alloc(0), { expectReply: false, beforeSend: () => enabled });
    h.flush();
    enabled = false;
    h.finishEncoding();
    await assert.rejects(pending, /取消/);
    assert.equal(h.packets.length, 0);
});

test('an enabled guarded write retains ordinary network dispatch behavior', async () => {
    const h = harness();
    const pending = h.api.sendMsgAsync('fixture.Service', 'Craft', Buffer.alloc(0), { expectReply: false, beforeSend: () => true });
    h.flush();
    await pending;
    assert.equal(h.packets.length, 1);
});

test('cancelling a reply-bearing write releases its pending slot and allows subsequent requests', async () => {
    for (const throws of [false, true]) {
        const h = harness({ pauseEncoding: true });
        const pending = h.api.sendMsgAsync('fixture.Service', 'Craft', Buffer.alloc(0), { beforeSend: () => {
            if (throws) throw new Error('guard cancelled');
            return false;
        } });
        h.flush();
        assert.equal(h.api.getGatewayLoad().pending, 1);
        h.finishEncoding();
        await assert.rejects(pending);
        assert.equal(h.api.getGatewayLoad().pending, 0);
        assert.equal(h.api.getGatewayLoad().queued, 0);
        await h.api.sendMsgAsync('fixture.Service', 'Read', Buffer.alloc(0), { expectReply: false });
        assert.equal(h.packets.length, 1);
    }
});
