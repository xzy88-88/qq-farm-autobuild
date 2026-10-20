const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const protobuf = require('protobufjs');
const root = new protobuf.Root().loadSync(path.join(__dirname, '../src/proto/activitypb.proto'), { keepCase: true });
const types = Object.fromEntries(['MilkTeaGetGroupReply', 'MilkTeaOperateReply', 'MilkTeaOperateRequest', 'GetGroupRequest'].map(name => [name, root.lookupType(`gamepb.activitypb.${name}`)]));
const encode = (type, data) => Buffer.from(type.encode(type.fromObject(data)).finish());

function harness() {
    const calls = [];
    const logs = [];
    const automation = { milk_tea_auto_upgrade: false, milk_tea_auto_craft: false };
    let reads = 0;
    let bagReads = 0;
    let onBagRead = () => {};
    let onDispatch = () => {};
    let now = 1792032000;
    let failRefresh = false;
    let writes = 0;
    let hireSucceeds = false;
    const milk = { head: { activity_id: '2026110101', name: '奶茶热销中', begin_time: 1792029600, end_time: 1794844799, settle_start_time: 1794671999 }, milk_tea: { summary: { shop_open_at: 1792030000, shop_name: '测试店铺', level: 1, total_revenue: 500 } } };
    const goods = { id: 301, item: [{ id: 20525, count: 1 }], cost: [{ id: 1001, count: 10000 }], purchase_limit: 108, purchased_count: 2, category_tag: 'seed', cond_hints: [] };
    const fund = { unlocked: false, unlock_cost: [{ id: 1004, count: 360 }], tiers: [{ tier_id: 1, state: 2, reward: [{ id: 1002, count: 288 }] }] };
    const bag = [{ id: 1042, count: 1 }, { id: 1041, count: 200 }, { id: 1001, count: 100000 }, { id: 40525, uid: 900, count: 20 }];
    const shop = { level: 1, sales_item_id: 1042, boost_cups_per_use: 40, drink_cups: { 2: 10 }, slots: [], pending_rewards: [{ id: 1041, count: 12 }] };
    const hireList = { duration_id: 1, wage_total: 40, min_remain_biz_sec: 600, friends: [], robots: [{ friend: { gid: 101, name: '实习员工' }, is_robot: true }] };
    const work = { hire_subscribe_qq_jump_url: 'private-signature', hire_subscribe_template_id: 'private-template' };
    const fields = { 55: 'milk_tea_get_shop', 56: 'milk_tea_get_hire_list', 58: 'milk_tea_get_workshop', 60: 'milk_tea_boost', 62: 'milk_tea_craft', 57: 'milk_tea_hire', 1: 'shop_buy', 75: 'growth_fund_unlock', 76: 'growth_fund_claim', 63: 'milk_tea_get_work_page' };
    Object.assign(fields, { 54: 'milk_tea_rename_shop', 61: 'milk_tea_upgrade', 68: 'milk_tea_set_hire_disable', 65: 'milk_tea_interact' });
    const mock = (name, exports) => { const id = require.resolve(`../dist/${name}`); require.cache[id] = { id, filename: id, loaded: true, exports }; };
    mock('utils/proto', { types });
    mock('utils/utils', { toNum: v => Number(v) || 0, getServerTimeSec: () => now, log: (...args) => logs.push(args) });
    mock('models/store', { getAutomation: () => ({ ...automation }) });
    mock('config/gameConfig', { getItemById: id => ({ name: `物品${id}` }), getItemImageById: () => '' });
    mock('services/pay', { getDiamondBalance: async () => 767 });
    mock('services/warehouse', { getBag: async () => { onBagRead(++bagReads); return { items: bag }; }, getBagItems: b => b.items, isItemLocked: v => !!v.locked });
    mock('utils/network', { sendMsgAsync: async (_service, method, body, options = {}) => {
        if (method === 'GetGroup') {
            reads++;
            if (failRefresh && writes) throw new Error('offline');
            return { body: encode(types.MilkTeaGetGroupReply, { group: { head: { activity_id: '2026110100' }, children: [milk, { head: { activity_id: '2026110102' }, shop: { goods: [goods] } }, { head: { activity_id: '2026110103' }, growth_fund: fund }] } }) };
        }
        const req = types.MilkTeaOperateRequest.toObject(types.MilkTeaOperateRequest.decode(body), { longs: String });
        const cmd = Number(req.operate_type);
        await onDispatch(cmd);
        if (options.beforeSend && !options.beforeSend()) throw new Error('请求已取消');
        let result;
        if (cmd === 55) result = { shop };
        else if (cmd === 58) result = { recipes: [{ recipe_id: 2, recipe_name: '甜莓奶茶', unlocked: true, is_advanced: true, stock_cups: 10 }] };
        else if (cmd === 56) result = hireList;
        else if (cmd === 63) result = work;
        else {
            calls.push(req); writes++;
            if (cmd === 60) { bag[0].count--; result = { cups: 40, token_gain: 183, coin_gain: 111375 }; }
            else if (cmd === 75) { fund.unlocked = true; result = {}; }
            else if (cmd === 76) { fund.tiers[0].state = 3; result = { claimed_tier_ids: [1], awards: [{ id: 1002, count: 288 }] }; }
            else if (cmd === 57) {
                if (!hireSucceeds) result = { results: [{ success: false, error_code: 1, error_msg: '员工状态已变化' }] };
                else {
                    const hire = req.milk_tea_hire.hires[0];
                    const coupon = bag.find(item => item.id === 1041);
                    coupon.count -= Number(hireList.wage_total);
                    shop.slots.push({ slot_index: Number(hire.slot_index), end_at: now + 14400 });
                    const hiredFriend = (hireList.friends || []).find(entry => String(entry.friend.gid) === String(hire.target_gid));
                    if (hiredFriend) hiredFriend.state = 1;
                    result = { results: [{ success: true, slot_index: Number(hire.slot_index), duration_id: Number(hire.duration_id), target_gid: hire.target_gid }] };
                }
            }
            else if (cmd === 62) { result = { crafted_cups: { 2: 20 }, drink_cups: { 2: 30 }, used_fruits: [bag[3]] }; bag[3].count = 0; }
            else if (cmd === 61) { milk.milk_tea.summary.level++; milk.milk_tea.summary.can_upgrade = false; shop.level++; result = {}; }
            else result = { awards: [{ id: 20525, count: 1 }] };
        }
        return { body: encode(types.MilkTeaOperateReply, { activity_id: req.activity_id, operate_type: cmd, [fields[cmd]]: result }) };
    } });
    const id = require.resolve('../dist/services/milk-tea'); delete require.cache[id];
    return { service: require(id), calls, bag, shop, fund, goods, work, hireList, logs, automation, summary: milk.milk_tea.summary, get reads() { return reads; }, onBagRead: fn => onBagRead = fn, onDispatch: fn => onDispatch = fn, setTime: v => now = v, failRefresh: () => failRefresh = true, allowHire: () => hireSucceeds = true };
}

test('milk tea queued writes cancel on switch changes and settlement before actual dispatch', async () => {
    for (const action of ['craft', 'upgrade']) {
        for (const change of ['disabled', 'settling']) {
            const h = harness();
            h.automation[`milk_tea_auto_${action}`] = true;
            h.summary.can_upgrade = true;
            h.onDispatch(async cmd => {
                if (cmd !== (action === 'craft' ? 62 : 61)) return;
                await Promise.resolve();
                if (change === 'disabled') h.automation[`milk_tea_auto_${action}`] = false;
                else h.setTime(1794672000);
            });
            await h.service.runMilkTeaAutomation();
            assert.equal(h.calls.length, 0);
            assert.equal(h.bag[3].count, 20);
        }
    }
});

test('milk tea automation stays disabled without activity or inventory requests', async () => {
    const h = harness();
    const result = await h.service.runMilkTeaAutomation?.();
    assert.equal(result?.status, 'disabled');
    assert.equal(h.reads, 0);
    assert.equal(h.calls.length, 0);
});

test('milk tea automation upgrades an eligible shop then crafts only ordinary unlocked fruit stacks', async () => {
    const h = harness();
    Object.assign(h.automation, { milk_tea_auto_upgrade: true, milk_tea_auto_craft: true });
    h.summary.can_upgrade = true;
    h.bag.push({ id: 40525, uid: 901, count: 10, locked: true }, { id: 40525, uid: 902, count: 10, mutant_types: [7] }, { id: 999, uid: 903, count: 10 });
    const result = await h.service.runMilkTeaAutomation?.();
    assert.deepEqual(h.calls.map(v => v.operate_type), ['61', '62']);
    assert.deepEqual(h.calls[1].milk_tea_craft.fruit_uids, ['900']);
    assert.equal(result?.craftedCups, 20);
    assert.equal(result?.upgraded, true);
    assert.equal(h.bag[4].count, 10);
    assert.ok(h.logs.length >= 2);
});

test('milk tea automation does not open shops or operate outside the business period', async () => {
    for (const scenario of ['unopened', 'settling', 'ended']) {
        const h = harness();
        Object.assign(h.automation, { milk_tea_auto_upgrade: true, milk_tea_auto_craft: true });
        h.summary.can_upgrade = true;
        if (scenario === 'unopened') h.summary.shop_open_at = 0;
        else h.setTime(scenario === 'settling' ? 1794672000 : 1794844800);
        const result = await h.service.runMilkTeaAutomation?.();
        assert.equal(result?.status, 'skipped');
        assert.equal(h.calls.length, 0);
    }
});

test('milk tea automation rechecks mutations and locks immediately before consuming fruit', async () => {
    for (const changed of ['mutation', 'lock', 'count']) {
        const h = harness();
        h.automation.milk_tea_auto_craft = true;
        h.onBagRead(count => {
            if (count !== 2) return;
            if (changed === 'mutation') h.bag[3].mutant_types = [8];
            else if (changed === 'lock') h.bag[3].locked = true;
            else h.bag[3].count = 19;
        });
        const result = await h.service.runMilkTeaAutomation?.();
        assert.equal(result?.status, 'error');
        assert.equal(h.calls.length, 0);
    }
});

test('milk tea automatic and manual crafting share a queue and never consume the same stack twice', async () => {
    const h = harness();
    h.automation.milk_tea_auto_craft = true;
    await Promise.allSettled([
        h.service.runMilkTeaAutomation?.(),
        h.service.operateMilkTeaActivity('craft', { fruits: [{ uid: '900', count: 20 }] }),
    ]);
    assert.equal(h.calls.length, 1);
    assert.equal(h.service.getMilkTeaAutomationState?.().craftedCups, 20);
});

test('milk tea automation stops queued actions after logout or disabling the switch', async () => {
    const h = harness();
    h.automation.milk_tea_auto_craft = true;
    let connected = true;
    h.onBagRead(() => connected = false);
    const result = await h.service.runMilkTeaAutomation?.(() => connected);
    assert.equal(result?.status, 'disabled');
    assert.equal(h.calls.length, 0);
});

test('milk tea automation preserves a successful upgrade when refresh fails and defers crafting', async () => {
    const h = harness();
    Object.assign(h.automation, { milk_tea_auto_upgrade: true, milk_tea_auto_craft: true });
    h.summary.can_upgrade = true;
    h.failRefresh();
    const result = await h.service.runMilkTeaAutomation?.();
    assert.equal(result?.upgraded, true);
    assert.deepEqual(h.calls.map(v => v.operate_type), ['61']);
});

test('milk tea automation cancels a write when disabled during its final inventory check', async () => {
    const h = harness();
    h.automation.milk_tea_auto_craft = true;
    h.onBagRead(count => { if (count === 2) h.automation.milk_tea_auto_craft = false; });
    await h.service.runMilkTeaAutomation();
    assert.equal(h.calls.length, 0);
});

test('milk tea automation backs off after an inventory change instead of immediately retrying', async () => {
    const h = harness();
    h.automation.milk_tea_auto_craft = true;
    h.onBagRead(count => { if (count === 2) h.bag[3].locked = true; });
    const failed = await h.service.runMilkTeaAutomation();
    const reads = h.reads;
    h.bag[3].locked = false;
    await h.service.runMilkTeaAutomation();
    assert.equal(h.reads, reads);
    assert.equal(h.calls.length, 0);
    h.setTime(failed.nextCheckAt);
    await h.service.runMilkTeaAutomation();
    assert.equal(h.calls.length, 1);
});

test('milk tea automation hires available friends into empty slots and skips robots', async () => {
    const h = harness();
    h.allowHire();
    h.automation.milk_tea_auto_hire = true;
    h.shop.level = 3;
    h.hireList.friends.push(
        { friend: { gid: 202, name: '阿青' }, is_robot: false, state: 0, rehire_available_at: 0 },
        { friend: { gid: 303, name: '小林' }, is_robot: false, state: 0, rehire_available_at: 0 },
    );
    const result = await h.service.runMilkTeaAutomation();
    assert.equal(result?.status, 'success');
    assert.equal(result?.hiredFriends, 2);
    assert.deepEqual(h.calls.map(call => call.operate_type), ['57', '57']);
    assert.deepEqual(h.calls.map(call => call.milk_tea_hire.hires[0].target_gid), ['202', '303']);
    assert.deepEqual(h.calls.map(call => call.milk_tea_hire.hires[0].duration_id), [1, 1]);
    assert.equal(h.bag.find(item => item.id === 1041).count, 120);
    assert.equal(h.calls.some(call => call.operate_type === '1'), false);
    assert.ok(h.logs.some(entry => entry[0] === '奶茶' && String(entry[1]).includes('阿青')));
});

test('milk tea automation does not hire robots, buy coupons, or fill a shop that is already staffed', async () => {
    for (const scenario of ['robots', 'broke', 'full']) {
        const h = harness();
        h.allowHire();
        h.automation.milk_tea_auto_hire = true;
        if (scenario === 'broke') {
            h.hireList.friends.push({ friend: { gid: 202, name: '阿青' }, is_robot: false, state: 0 });
            h.bag.find(item => item.id === 1041).count = 39;
        } else if (scenario === 'full') {
            h.hireList.friends.push({ friend: { gid: 202, name: '阿青' }, is_robot: false, state: 0 });
            h.shop.slots.push({ slot_index: 0, end_at: 1792042000 });
        }
        const result = await h.service.runMilkTeaAutomation();
        assert.equal(result?.status, 'skipped', scenario);
        assert.equal(h.calls.length, 0, scenario);
        assert.equal(h.bag.find(item => item.id === 1041).count, scenario === 'broke' ? 39 : 200, scenario);
    }
});

test('milk tea automation cancels a hire before dispatch when the switch is turned off', async () => {
    const h = harness();
    h.allowHire();
    h.automation.milk_tea_auto_hire = true;
    h.hireList.friends.push({ friend: { gid: 202, name: '阿青' }, is_robot: false, state: 0 });
    h.onDispatch(cmd => { if (cmd === 57) h.automation.milk_tea_auto_hire = false; });
    const result = await h.service.runMilkTeaAutomation();
    assert.equal(result?.status, 'disabled');
    assert.equal(h.calls.length, 0);
    assert.equal(h.bag.find(item => item.id === 1041).count, 200);
});

test('boost spends the checked horn once and returns actual awards, retaining success after refresh failure', async () => {
    const h = harness();
    const state = await h.service.getMilkTeaActivity();
    assert.deepEqual(state.shop.drink_cups, { 2: 10 });
    h.failRefresh();
    const result = await h.service.operateMilkTeaActivity('boost', { count: 1, expectedCosts: [{ id: 1042, count: 1 }] });
    assert.equal(result.refreshRequired, true);
    assert.deepEqual(result.rewards.map(v => [v.id, v.count]), [[1041, 183], [1001, 111375]]);
    assert.deepEqual(h.calls[0].milk_tea_boost, { count: 1 });
    assert.equal(h.bag[0].count, 0);
});
test('boost rejects insufficient horns, changed prices and settlement without sending writes', async () => {
    const h = harness();
    await assert.rejects(h.service.operateMilkTeaActivity('boost', { count: 2, expectedCosts: [{ id: 1042, count: 1 }] }), /不足/);
    await assert.rejects(h.service.operateMilkTeaActivity('boost', { count: 1, expectedCosts: [{ id: 1004, count: 1 }] }), /费用已变化/);
    h.setTime(1794672000);
    await assert.rejects(h.service.operateMilkTeaActivity('boost', { count: 1 }), /结算期/);
    assert.equal(h.calls.length, 0);
});
test('craft consumes complete UID stacks and rejects locked, changed or duplicate selections', async () => {
    const h = harness();
    for (const fruits of [[{ uid: '900', count: 19 }], [{ uid: '900', count: 20 }, { uid: '900', count: 20 }]]) await assert.rejects(h.service.operateMilkTeaActivity('craft', { fruits }));
    h.bag[3].locked = true;
    await assert.rejects(h.service.operateMilkTeaActivity('craft', { fruits: [{ uid: '900', count: 20 }] }), /锁定状态/);
    h.bag[3].locked = false;
    const result = await h.service.operateMilkTeaActivity('craft', { fruits: [{ uid: '900', count: 20 }] });
    assert.deepEqual(result.result.crafted_cups, { 2: 20 });
    assert.deepEqual(h.calls[0].milk_tea_craft, { fruit_uids: ['900'] });
});
test('shop retains finite limits and enforces level, price and settlement conditions', async () => {
    const h = harness();
    assert.equal((await h.service.getMilkTeaActivity('exchange')).goods[0].remaining, 106);
    h.goods.cond_hints = [{ cond_type: 'level', current: 1, target: 3, satisfied: false }];
    await assert.rejects(h.service.operateMilkTeaActivity('exchange', { goodsId: 301, count: 1, expectedCosts: h.goods.cost }), /条件/);
    h.goods.cond_hints = [];
    await assert.rejects(h.service.operateMilkTeaActivity('exchange', { goodsId: 301, count: 1, expectedCosts: [{ id: 1001, count: 1 }] }), /费用已变化/);
    h.setTime(1794672000);
    await assert.rejects(h.service.operateMilkTeaActivity('exchange', { goodsId: 301, count: 1, expectedCosts: h.goods.cost }), /条件/);
    assert.equal(h.calls.length, 0);
});
test('fund unlock is serialized and claims require paid unlock without duplicate charges', async () => {
    const h = harness();
    await assert.rejects(h.service.operateMilkTeaActivity('fundClaim'), /暂无/);
    const results = await Promise.allSettled([1, 2].map(() => h.service.operateMilkTeaActivity('unlock', { expectedCosts: [{ id: 1004, count: 360 }] })));
    assert.deepEqual(results.map(v => v.status), ['fulfilled', 'rejected']);
    assert.equal(h.calls.length, 1);
    assert.deepEqual(h.calls[0], { activity_id: '2026110103', operate_type: '75' });
    const result = await h.service.operateMilkTeaActivity('fundClaim');
    assert.equal(result.rewards[0].count, 288);
    await assert.rejects(h.service.operateMilkTeaActivity('fundClaim'), /暂无/);
});
test('hire partial failures are not reported as success and signed work links stay private', async () => {
    const h = harness();
    await assert.rejects(h.service.operateMilkTeaActivity('hire', { targetGid: '101', slotIndex: 0, durationId: 1, expectedCosts: [{ id: 1041, count: 40 }] }), /员工状态/);
    assert.deepEqual(h.calls[0].milk_tea_hire.hires[0], { slot_index: 0, duration_id: 1, target_gid: '101' });
    const state = await h.service.getMilkTeaActivity('work');
    assert.equal(JSON.stringify(state).includes('private-'), false);
});

test('hire automatically chooses a freshly vacant unlocked slot and rejects a full shop', async () => {
    const h = harness();
    h.shop.level = 3;
    h.shop.slots = [{ slot_index: 0, end_at: 1792042000 }];
    const input = { targetGid: '101', durationId: 1, expectedCosts: [{ id: 1041, count: 40 }] };
    await assert.rejects(h.service.operateMilkTeaActivity('hire', input), /员工状态/);
    assert.equal(h.calls[0].milk_tea_hire.hires[0].slot_index, 1);
    h.shop.slots.push({ slot_index: 1, end_at: 1792042000 });
    await assert.rejects(h.service.operateMilkTeaActivity('hire', input), /位置已满/);
    assert.equal(h.calls.length, 1);
    h.shop.slots[0].end_at = 1792031000;
    await assert.rejects(h.service.operateMilkTeaActivity('hire', input), /员工状态/);
    assert.equal(h.calls.at(-1).milk_tea_hire.hires[0].slot_index, 0);
});

test('settings validate the current shop and preserve boolean hire mode in the wire request', async () => {
    const h = harness();
    await assert.rejects(h.service.operateMilkTeaActivity('hireSetting', { disabled: 'false' }), /无效/);
    for (const disabled of [true, false]) {
        await h.service.operateMilkTeaActivity('hireSetting', { disabled });
        assert.equal(h.calls.at(-1).milk_tea_set_hire_disable.hire_disabled, disabled);
    }
    h.summary.rename_cd_until_at = 1792033000;
    await assert.rejects(h.service.operateMilkTeaActivity('rename', { name: '奶茶补给站' }), /修改店名时间/);
    h.summary.shop_open_at = 0;
    await assert.rejects(h.service.operateMilkTeaActivity('boost', { count: 1 }), /先开业/);
    assert.equal(h.calls.length, 2);
});

test('upgrade uses fresh eligibility and rejects stale levels before sending a request', async () => {
    const h = harness();
    await assert.rejects(h.service.operateMilkTeaActivity('upgrade', { expectedLevel: 1 }), /升级条件/);
    h.summary.can_upgrade = true;
    await assert.rejects(h.service.operateMilkTeaActivity('upgrade', { expectedLevel: 2 }), /等级已变化/);
    const preview = await h.service.getMilkTeaActivity('upgrade');
    assert.ok(preview.levels[1].rewards.length);
    await h.service.operateMilkTeaActivity('upgrade', { expectedLevel: 1 });
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].operate_type, '61');
});

test('work interactions validate the displayed shift and preview before submitting, and block expired or spent shifts', async () => {
    const h = harness();
    h.work.my_shift = { employer: { gid: '101' }, shift_id: '7', begin_at: 1792031000, end_at: 1792045400, interact_limit: 1, interact_count: 0, interact_previews: [{ interaction_type: 1, promote_cups: 40 }] };
    await assert.rejects(h.service.operateMilkTeaActivity('interact', { interactionType: 1, expectedShiftId: '6' }), /班次已变化/);
    h.work.my_shift.interact_previews = [];
    await assert.rejects(h.service.operateMilkTeaActivity('interact', { interactionType: 1, expectedShiftId: '7' }), /数据不完整/);
    assert.equal(h.calls.length, 0);
    await h.service.operateMilkTeaActivity('interact', { interactionType: 3, expectedShiftId: '7' });
    assert.deepEqual(h.calls[0].milk_tea_interact, { target_gid: '101', interaction_type: 3 });
    h.work.interact_done = true;
    await assert.rejects(h.service.operateMilkTeaActivity('interact', { interactionType: 4, expectedShiftId: '7' }), /不可互动/);
    h.work.interact_done = false;
    h.setTime(1792045400);
    await assert.rejects(h.service.operateMilkTeaActivity('interact', { interactionType: 4, expectedShiftId: '7' }), /不可互动/);
    assert.equal(h.calls.length, 1);
});
