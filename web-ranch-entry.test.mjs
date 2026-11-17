import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'

const require = createRequire(import.meta.url)
const ts = require('typescript')

function loadIndex() {
  const source = readFileSync(new URL('../src/components/activity/gameplays/index.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  })
  const module = { exports: {} }
  const imports = {
    './charity': { charityGameplay: { key: 'charity', defaultTab: 'charity', tabs: ['charity'] } },
    './pet': { petGameplay: { key: 'pet', defaultTab: 'pet', tabs: ['pet'] } },
    './qingmei': { qingMeiGameplay: { key: 'qingmei', defaultTab: 'qingmei', tabs: ['qingmei'] } },
    './qixi': { qixiGameplay: { key: 'qixi', defaultTab: 'qixi', tabs: ['qixi'] } },
    './stellar': { stellarGameplay: { key: 'stellar', defaultTab: 'travel', tabs: ['travel', 'constellation', 'shop', 'solar'] } },
    './weather': { weatherGameplay: { key: 'weather', defaultTab: 'weather', tabs: ['weather'] } },
  }
  new Function('require', 'module', 'exports', outputText)(id => imports[id] || require(id), module, module.exports)
  return module.exports
}

const { resolveActivityGameplay, activityHasGameplay } = loadIndex()

function activity(id, name, overrides = {}) {
  return {
    id,
    activityIds: [id],
    name,
    startTime: null,
    endTime: null,
    gameplayKey: null,
    gameplayTargets: [],
    detailTarget: null,
    ...overrides,
  }
}

test('牧歌初启 opens ranch activity from the farm activity center', () => {
  for (const id of ['2026111700', '2026111702', '2026111703', '2026111704', '2026111705']) {
    const resolved = resolveActivityGameplay(activity(id, '牧歌初启'))
    assert.equal(resolved?.module.key, 'ranch', id)
    assert.equal(resolved?.entryTab, 'ranch', id)
    assert.equal(activityHasGameplay(activity(id, '牧歌初启')), true, id)
  }
  const byName = resolveActivityGameplay(activity('future-id', '牧歌初启'))
  assert.equal(byName?.module.key, 'ranch')
  const byDetailTarget = resolveActivityGameplay(activity('future-id', 'other', { detailTarget: 'ranch' }))
  assert.equal(byDetailTarget?.module.key, 'ranch')
})

test('unrelated November 17 activities are not classified as ranch gameplay', () => {
  for (const [id, name] of [['2026111707', '以薯换福'], ['2026111708', '枫叶集市']]) {
    assert.equal(resolveActivityGameplay(activity(id, name)), null, id)
    assert.equal(activityHasGameplay(activity(id, name)), false, id)
  }
})

test('existing gameplay inference is unchanged', () => {
  assert.equal(resolveActivityGameplay(activity('2026110100', '奶茶热销中', { gameplayKey: 'milk', detailTarget: 'milk' }))?.module.key, 'milk')
  assert.equal(resolveActivityGameplay(activity('2026090100', '萌宠成长日记'))?.module.key, 'pet')
  assert.equal(resolveActivityGameplay(activity('2026072700', '心许千灯星垂野'))?.module.key, 'stellar')
  assert.equal(resolveActivityGameplay(activity('2026070300', '雨落成诗'))?.module.key, 'weather')
})

test('ranch activity detail opens the ranch page without an activity detail request', () => {
  const source = readFileSync(new URL('../src/views/ActivityCenter.vue', import.meta.url), 'utf8')
  const openActivity = source.slice(source.indexOf('async function openActivity'), source.indexOf('function goBack'))
  assert.match(openActivity, /gameplay\.module\.key === 'ranch'/)
  assert.match(openActivity, /router\.push\('\/ranch\/activity'\)/)
  assert.ok(openActivity.indexOf("module.key === 'ranch'") < openActivity.indexOf('loadDetails'), 'ranch must return before loadDetails')
})
