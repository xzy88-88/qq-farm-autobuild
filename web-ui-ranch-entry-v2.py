"""Patch cloned upstream web sources so 牧歌初启 opens the ranch activity page.

This script is intentionally idempotent. It only touches web UI files in the
temporary build source tree; core game, transaction and receiver behavior stay
under the existing maintained patch and installer.
"""
from pathlib import Path

root = Path('source')


def replace(path, old, new):
    target = root / path
    source = target.read_text(encoding='utf-8')
    if new in source:
        return
    if source.count(old) != 1:
        raise RuntimeError(f'Ranch activity entry patch needs review: {path}')
    target.write_text(source.replace(old, new, 1), encoding='utf-8')


def replace_all(path, old, new, expected):
    target = root / path
    source = target.read_text(encoding='utf-8')
    if source.count(old) != expected:
        raise RuntimeError(f'Ranch activity entry patch needs review: {path} ({source.count(old)} != {expected})')
    target.write_text(source.replace(old, new), encoding='utf-8')


store = root / 'web/src/stores/activity-center.ts'
source = store.read_text(encoding='utf-8')
if "| 'ranch'" not in source:
    replacements = [
        ("export type ActivityTabKey = 'travel' | 'constellation' | 'shop' | 'solar' | 'qixi' | 'qingmei' | 'charity' | 'weather' | 'pet' | 'wish' | 'happy' | 'milk'",
         "export type ActivityTabKey = 'travel' | 'constellation' | 'shop' | 'solar' | 'qixi' | 'qingmei' | 'charity' | 'weather' | 'pet' | 'wish' | 'happy' | 'milk' | 'ranch'"),
        ("export type ActivityGameplayKey = 'stellar' | 'qixi' | 'qingmei' | 'charity' | 'weather' | 'pet' | 'wish' | 'happy' | 'milk'",
         "export type ActivityGameplayKey = 'stellar' | 'qixi' | 'qingmei' | 'charity' | 'weather' | 'pet' | 'wish' | 'happy' | 'milk' | 'ranch'"),
        ("['travel', 'constellation', 'shop', 'solar', 'qixi', 'qingmei', 'charity', 'weather', 'pet', 'wish', 'happy', 'milk']",
         "['travel', 'constellation', 'shop', 'solar', 'qixi', 'qingmei', 'charity', 'weather', 'pet', 'wish', 'happy', 'milk', 'ranch']"),
        ("                      : gameplayKey === 'stellar' || normalizedDetailTarget\n                        ? 'stellar' as const\n                        : null,",
         "                      : gameplayKey === 'ranch' || normalizedDetailTarget === 'ranch'\n                        ? 'ranch' as const\n                        : gameplayKey === 'stellar' || normalizedDetailTarget\n                          ? 'stellar' as const\n                          : null,"),
    ]
    for old, new in replacements:
        expected = 2 if old.startswith("['travel'") else 1
        if source.count(old) != expected:
            raise RuntimeError(f'Store ranch activity patch needs review: {old[:48]} ({source.count(old)} != {expected})')
        source = source.replace(old, new)
    store.write_text(source, encoding='utf-8')

gameplays = root / 'web/src/components/activity/gameplays/index.ts'
source = gameplays.read_text(encoding='utf-8')
if 'const RANCH_ACTIVITY_IDS' not in source:
    marker = "const gameplayModules: Record<ActivityGameplayKey, ActivityGameplayModule> = {\n"
    ranch_module = "const RANCH_ACTIVITY_IDS = new Set(['2026111700', '2026111702', '2026111703', '2026111704', '2026111705'])\nconst ranchGameplay: ActivityGameplayModule = { key: 'ranch', defaultTab: 'ranch', tabs: ['ranch'] }\n\n"
    if source.count(marker) != 1:
        raise RuntimeError('Ranch gameplay module insertion point changed')
    source = source.replace(marker, ranch_module + marker, 1)
    source = source.replace("  weather: weatherGameplay,\n}", "  weather: weatherGameplay,\n  ranch: ranchGameplay,\n}", 1)
    old = "function inferGameplayKey(activity: ActivityDirectoryItemDto): ActivityGameplayKey | null {\n  if (activity.detailTarget === 'wish' || activity.detailTarget === 'happy')\n"
    new = "function inferGameplayKey(activity: ActivityDirectoryItemDto): ActivityGameplayKey | null {\n  if (activity.detailTarget === 'ranch' || activity.gameplayKey === 'ranch' || activity.name.trim() === '牧歌初启' || activity.activityIds.some(id => RANCH_ACTIVITY_IDS.has(id.trim())))\n    return 'ranch'\n  if (activity.detailTarget === 'wish' || activity.detailTarget === 'happy')\n"
    if source.count(old) != 1:
        raise RuntimeError('Ranch gameplay inference insertion point changed')
    source = source.replace(old, new, 1)
    gameplays.write_text(source, encoding='utf-8')
replace(
    'web/src/views/ActivityCenter.vue',
    "  if (!gameplay)\n    return\n  if (gameplay.module.key === 'stellar')",
    "  if (!gameplay)\n    return\n  if (gameplay.module.key === 'ranch') {\n    await router.push('/ranch/activity')\n    return\n  }\n  if (gameplay.module.key === 'stellar')",
)

print('RANCH_ACTIVITY_ENTRY_V2_PATCHED')
