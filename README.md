# qq-farm-autobuild
自动跟踪 liyangpengs/qq-farm-bot 的 master 更新，云端构建并发布部署包。仓库不包含服务器凭据、农场账号或运行设置。


2026-10-23: v3 adds opt-in automatic friend hiring, configurable duration and a coupon reserve. Existing accounts remain opted out. The receiver migrates known v1/v2 installations while preserving transactional backup/rollback and LOGIN_FAILED hooks.

2026-10-28: v4 preserves v3 milk-tea automation and adds not-friend (1001048) farming protection: stop fallback/remaining actions, refresh the friend list, cool down only the affected target for ten minutes, retain confirmed partial success, and preserve friend/account settings.
