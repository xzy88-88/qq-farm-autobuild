# Bounded network recovery

User selected direct implementation on 2026-10-30. Preserve the installed v4
application, old guard, accounts, settings, and shared QQ services.

1. Test the recovery state machine before implementation. Only account 2 can be
   enabled. Require a previously observed online session and a later network
   disconnect; manual stops, kickouts, changed credentials and identity mismatch
   must not cause a restart. Consume events before auth; cap at three/hour and
   ten-minute spacing.
2. Implement a separate Python maintenance helper using existing authenticated
   panel endpoints and read-only QQ profile lookup. Never reuse old Code, cancel
   a QR task, log out QQ, or log credentials. Recheck identity and account/event
   state before updating Code. Install a deployment-lock-aware systemd timer.
3. Run all helper and existing guard tests. Review the result independently.
   Back up files before installation and bind only the currently verified QQ
   identity while account 2 is online. Verify dry-run arming and timer operation
   without deliberately disconnecting the real game account.
4. Check real game replies, milk tea status, configuration preservation and
   updater/guard identity. Document that reconnection mitigates an external
   no-reply episode; its original cause remains unproven.
