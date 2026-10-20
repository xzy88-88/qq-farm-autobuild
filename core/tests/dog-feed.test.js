const test = require('node:test');
const assert = require('node:assert/strict');
const { loadProto, types } = require('../dist/utils/proto');
const { normalizeAccountConfig, globalConfig } = require('../dist/models/store/shared-state');

const FOOD_DURATION = { 90004: 86400, 90005: 259200, 90006: 432000 };

function harness() {
    const calls = [];
    const logs = [];
    const automation = { dog_auto_feed: false };
    let protect = 0;
    let currentDog = 90001;
    let now = 1792032000;
    let reads = 0;
    let rejectSend = false;
    let onRead = () => {};
    const bag = [
        { id: 90004, uid: 1, count: 2 },
        { id: 90006, uid: 2, count: 1 },
    ];
    const mock = (name, exports) => {
        const id = require.resolve(`../dist/${name}`);
        require.cache[id] = { id, filename: id, loaded: true, exports };
    };
    mock('utils/utils', {
        toNum: value => Number(value) || 0,
        getServerTimeSec: () => now,
        log: (...args) => logs.push(args),
        logWarn: (...args) => logs.push(args),
    });
    mock('models/store', { getAutomation: () => ({ ...automation }) });
    mock('config/gameConfig', {
        getItemById: id => ({ name: id === 90004 ? '一天狗粮' : id === 90006 ? '五天狗粮' : `物品${id}` }),
        getItemImageById: () => '',
    });
    mock('services/warehouse', {
        getBag: async () => ({ items: bag }),
        getBagItems: reply => reply.items,
        isItemLocked: item => !!item.locked,
    });
    mock('services/dog-skill-gifts', {
        getDogInfo: async () => {
            reads++;
            onRead(reads);
            return { current_dog_id: currentDog, protect_time: protect, max_protect_time: 2592000, dogs: [], items: [] };
        },
    });
    mock('utils/network', {
        sendMsgAsync: async (service, method, body, options = {}) => {
            if (rejectSend) throw new Error('服务器拒绝');
            if (options.beforeSend && !options.beforeSend()) throw new Error('请求已取消');
            const request = types.AddFoodRequest.toObject(types.AddFoodRequest.decode(body), { longs: String });
            calls.push({ service, method, request });
            const duration = FOOD_DURATION[Number(request.item_id)] * Number(request.count);
            const item = bag.find(entry => entry.id === Number(request.item_id) && !entry.locked);
            if (!item || item.count < Number(request.count)) throw new Error('库存不足');
            item.count -= Number(request.count);
            protect += duration;
            return { body: Buffer.from(types.AddFoodReply.encode(types.AddFoodReply.fromObject({ protect_time: protect })).finish()) };
        },
    });
    const id = require.resolve('../dist/services/pets');
    delete require.cache[id];
    return {
        service: require(id),
        calls,
        logs,
        bag,
        automation,
        get reads() { return reads; },
        get protect() { return protect; },
        setProtect: value => protect = value,
        setDog: value => currentDog = value,
        setTime: value => now = value,
        onRead: fn => onRead = fn,
        rejectSend: () => rejectSend = true,
    };
}

test('dog food automation is opt-in and does not read the farm while disabled', async () => {
    await loadProto();
    const defaults = normalizeAccountConfig({}).automation;
    assert.equal(defaults.dog_auto_feed, false);
    const h = harness();
    const result = await h.service.runDogFoodAutomation();
    assert.equal(result?.status, 'disabled');
    assert.equal(result?.autoFeed, false);
    assert.equal(h.reads, 0);
    assert.equal(h.calls.length, 0);
    delete globalConfig.accountConfigs.__dog_feed;
});

test('dog food automation feeds one shortest unlocked portion only when protection has run out', async () => {
    await loadProto();
    const h = harness();
    h.automation.dog_auto_feed = true;
    const fed = await h.service.runDogFoodAutomation();
    assert.equal(fed?.status, 'success');
    assert.equal(fed?.fedItemId, 90004);
    assert.equal(fed?.fedCount, 1);
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].service, 'gamepb.dogpb.DogService');
    assert.equal(h.calls[0].method, 'AddFood');
    assert.equal(String(h.calls[0].request.item_id), '90004');
    assert.equal(String(h.calls[0].request.count), '1');
    assert.equal(h.bag[0].count, 1);
    assert.equal(h.bag[1].count, 1);
    assert.equal(h.protect, 86400);
    const skipped = await h.service.runDogFoodAutomation();
    assert.equal(skipped?.status, 'skipped');
    assert.equal(h.calls.length, 1);
    assert.ok(h.logs.some(entry => String(entry[1]).includes('自动喂食')));
});

test('dog food automation skips a deployed dog that still has food, an empty bowl without stock, and a kennel with no dog', async () => {
    await loadProto();
    for (const scenario of ['remaining', 'empty', 'no-dog', 'locked']) {
        const h = harness();
        h.automation.dog_auto_feed = true;
        if (scenario === 'remaining') h.setProtect(120);
        if (scenario === 'empty') h.bag.splice(0, h.bag.length);
        if (scenario === 'no-dog') h.setDog(0);
        if (scenario === 'locked') h.bag.forEach(item => item.locked = true);
        const result = await h.service.runDogFoodAutomation();
        assert.equal(result?.status, 'skipped', scenario);
        assert.equal(h.calls.length, 0, scenario);
        assert.equal(result?.autoFeed, true, scenario);
    }
});

test('dog food automation uses the next shortest unlocked food and cancels before sending when disabled', async () => {
    await loadProto();
    const locked = harness();
    locked.automation.dog_auto_feed = true;
    locked.bag[0].locked = true;
    const fed = await locked.service.runDogFoodAutomation();
    assert.equal(fed?.fedItemId, 90006);
    assert.equal(String(locked.calls[0].request.item_id), '90006');
    assert.equal(locked.bag[0].count, 2);

    const cancelled = harness();
    cancelled.automation.dog_auto_feed = true;
    cancelled.onRead(count => { if (count >= 2) cancelled.automation.dog_auto_feed = false; });
    const result = await cancelled.service.runDogFoodAutomation();
    assert.equal(result?.status, 'disabled');
    assert.equal(cancelled.calls.length, 0);
    assert.equal(cancelled.bag[0].count, 2);
});

test('dog food automation backs off after a rejected feed instead of retrying immediately', async () => {
    await loadProto();
    const h = harness();
    h.automation.dog_auto_feed = true;
    h.rejectSend();
    const failed = await h.service.runDogFoodAutomation();
    assert.equal(failed?.status, 'error');
    assert.equal(h.calls.length, 0);
    const reads = h.reads;
    const duringBackoff = await h.service.runDogFoodAutomation();
    assert.equal(duringBackoff?.status, 'error');
    assert.equal(h.reads, reads);
    assert.ok(failed.nextCheckAt > 1792032000);
});
