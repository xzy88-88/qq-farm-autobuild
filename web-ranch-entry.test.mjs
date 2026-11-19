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
const { buildActivityGameplayBindings, resolveActivityGameplays } = require('../../core/dist/services/activity-gameplay-registry')
const bindings = buildActivityGameplayBindings({})

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

test('牧歌初启 bindings from the backend open the native activity page', () => {
  for (const id of ['2026111700', '2026111702', '2026111703', '2026111704', '2026111705']) {
    const entry = activity(id, '牧歌初启', resolveActivityGameplays([id], bindings))
    const resolved = resolveActivityGameplay(entry)
    assert.equal(resolved?.module.key, 'muge', id)
    assert.equal(resolved?.entryTab, 'muge', id)
    assert.equal(activityHasGameplay(entry), true, id)
  }
  const source = readFileSync(new URL('../src/views/ActivityCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /<MugePage v-else-if="selectedActivity === 'muge'"/)
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
