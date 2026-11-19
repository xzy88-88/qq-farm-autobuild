const assert = require('node:assert/strict')
const { resolve } = require('node:path')
const { RANCH_AUTOMATION_DEFAULTS: defaults } = require(resolve(process.argv[2], 'core/dist/config/ranch-automation'))

for (const key of ['ranch_buy', 'ranch_grass_buy', 'ranch_upgrade'])
  assert.equal(defaults[key], false, key)

const enabled = Object.keys(defaults).filter(key => defaults[key] === true)
assert.deepEqual(enabled.sort(), ['ranch_share', 'ranch_task'])
