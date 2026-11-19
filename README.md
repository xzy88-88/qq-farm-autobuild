# qq-farm-autobuild
自动跟踪 liyangpengs/qq-farm-bot 的 master 更新，云端构建并发布部署包。仓库不包含服务器凭据、农场账号或运行设置。

2026-11-19: GitHub Actions polls upstream master on a 15-minute schedule. It applies the maintained patch using Git’s three-way merge, tests upstream’s native 牧歌初启 page, and preserves opt-in ranch actions. Conflicts and unexpected test failures stop publication. The server’s existing timer picks up the verified release using the v2 receiver.

2026-11-17: `ranch-maintained-v2` adds a farm activity-center entry that opens the existing ranch activity page for 牧歌初启. It keeps the v1 scope: current upstream ranch functionality with only the existing friend-1001048 cooldown and bounded network-recovery fences, QQ login/Qmsg compatibility, and refreshed upstream test fixtures. The transactional receiver migrates v1 to v2 with `install-ranch-receiver.py`; milk tea automation remains disabled in the existing account settings. The original five client/TSDK audit warnings remain explicit; additional test failures block publication.


2026-10-23: v3 adds opt-in automatic friend hiring, configurable duration and a coupon reserve. Existing accounts remain opted out. The receiver migrates known v1/v2 installations while preserving transactional backup/rollback and LOGIN_FAILED hooks.

2026-10-28: v4 preserves v3 milk-tea automation and adds not-friend (1001048) farming protection: stop fallback/remaining actions, refresh the friend list, cool down only the affected target for ten minutes, retain confirmed partial success, and preserve friend/account settings.

2026-11-02: follow upstream `master` as the live source again. `milk-tea-auto-v5-web.patch` is the cumulative patch rebased onto upstream 20261101 (`1b7dd3f`) and restores the four frontend files that the v5 patch had dropped (settings switches, store types, settings defaults, milk-tea status line). The capability label and release tag stay `milk-tea-auto-v5` because the receiver validates that exact value and the capability contract did not change. Polling is every 30 minutes.

2026-11-02: upstream 20261101 bumps the pinned client/TSDK audits without refreshing the matching assertions, so `core test` reports five baseline drifts. `ci/core-test-gate.py` lets those five audited baselines through with a GitHub warning while every other failing test still blocks the build. Manual `workflow_dispatch` accepts `dry_run=true` to build and smoke-test without publishing a release, so a candidate can be checked before the server timer can see it.
