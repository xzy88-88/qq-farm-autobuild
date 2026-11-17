# Maintained Ranch Upgrade Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the existing server to upstream ranch version 20261117 while preserving the original accounts, settings, QQ authorization, friend protection and bounded network recovery; keep retired milk tea automation disabled.

**Architecture:** Build the latest upstream commit in the existing GitHub repository. Replace the obsolete cumulative milk tea patch with a minimal compatibility patch and a new `ranch-maintained-v1` release capability. Migrate only the existing receiver's capability contract and fetch defect, preserving its transaction/backup/rollback functions and login compatibility hooks.

**Tech Stack:** TypeScript/Vue, Python updater, Docker, GitHub Actions, existing Aliyun command assistant.

**Spec:** User's explicit request to update immediately, plus the verified scope in PROJECT_STATE.md and ranch-check-20261117/牧场开放与项目支持核对.md.

## Global Constraints

- Preserve account IDs 1 and 2, settings and named data/log volumes; restore only accounts running immediately before deployment.
- Preserve LOGIN_FAILED handling, confirmed-without-QR, Qmsg v3, per-friend 1001048 cooldown and network-recovery manual-action fences.
- Keep all three milk tea switches false for both accounts.
- Do not restart/rebuild NapCat or change its identity, plugins, credentials or shared group-alert configuration.
- Run builds on GitHub, not the 2 GB server; use the existing transactional deployment and private backups.
- No Serena. No new default spending behavior from ranch controls before the user's settings are verified.

## Review Focus

- A manual stop, kickout, updated code or changed identity must fence stale automatic recovery.
- Partial friend success followed by 1001048 must retain statistics and stop retries for that target.
- New settings defaults must not reactivate retired milk tea switches or automatically spend ranch currencies.
- A cloud build or checksum/canary failure must preserve the existing application and data.
- Receiver migration must preserve original transaction function AST and LOGIN_FAILED prepare hook.

## Task 1: Maintained ranch build

- [ ] Record clean baseline tests in the existing build repository.
- [ ] Apply only network-fence and friend-1001048 commits to a fresh upstream branch; resolve against current source and run their behavior tests plus the current core/web checks.
- [ ] Add build-contract regression tests that fail for the old milk-dependent pipeline.
- [ ] Update CI to build and verify `ranch-maintained-v1`, with truthful labels/manifest and no required milk capability.

## Task 2: Receiver migration

- [ ] Add tests for migration from the installed v5 receiver and preservation of transaction functions/login hooks; watch failure before implementation.
- [ ] Implement validated, backed-up migration to the new capability and isolated ranch/fence smoke checks.
- [ ] Diagnose current git-fetch failure and implement the smallest evidence-backed correction.
- [ ] Run receiver and recovery test suites; request independent compatibility review before shared-branch publication.

## Task 3: Build, deploy, verify

- [ ] Commit and publish the reviewed build configuration, follow CI to completion and verify the release manifest.
- [ ] Back up existing server updater/configuration; run candidate checks using original canary and deployment workflow.
- [ ] Complete transactional deployment and recover only the previous running account via existing authorized QQ session when needed.
- [ ] Verify version, ranch page/read endpoints, account 2 connection, all milk switches false, original guards/volumes/settings and active timers.
- [ ] Save screenshot, evidence, backup pointers and updated project state. Keep checking until the requested update is actually usable or a concrete user-only authentication blocker is reached.
