const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeAccountConfig, globalConfig } = require('../dist/models/store/shared-state');
const { applyConfigSnapshot } = require('../dist/models/store/account-config');

test('milk tea automation is opt-in and remains isolated per account across config round trips', () => {
    const defaults = normalizeAccountConfig({}).automation;
    assert.equal(defaults.milk_tea_auto_upgrade, false);
    assert.equal(defaults.milk_tea_auto_craft, false);
    try {
        const first = applyConfigSnapshot({ automation: { milk_tea_auto_upgrade: true, milk_tea_auto_craft: true } }, { accountId: '__milk_a', persist: false });
        applyConfigSnapshot({ automation: { milk_tea_auto_upgrade: false, milk_tea_auto_craft: false } }, { accountId: '__milk_b', persist: false });
        assert.equal(first.automation.milk_tea_auto_craft, true);
        assert.equal(normalizeAccountConfig(globalConfig.accountConfigs.__milk_a).automation.milk_tea_auto_upgrade, true);
        assert.equal(normalizeAccountConfig(globalConfig.accountConfigs.__milk_b).automation.milk_tea_auto_craft, false);
    } finally {
        delete globalConfig.accountConfigs.__milk_a;
        delete globalConfig.accountConfigs.__milk_b;
    }
});
