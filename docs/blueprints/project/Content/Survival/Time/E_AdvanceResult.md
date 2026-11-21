# E_AdvanceResult — outcome of an explicit clock request

Package: /Game/Survival/Time/E_AdvanceResult
AssetType: Blueprint Enumeration
DependsOn: none
Status: NEEDS REVIEW; no UE/MCP/PIE verification, 21.11.2026.

Create Content Browser → Blueprints → Enumeration with EXACT entries in this order:
- NotAttempted — initial value before any advance.
- Completed — all registered receivers acknowledged every step; request elapsed fully.
- Rejected — validation failed before any time mutation.
- PartialFailure — at least one part of dispatch began and a receiver reported failure; the session is now faulted.

Usage: Return pin on BP_SurvivalWorld.AdvanceGameTime; test fixture checks result == Completed. Result is not a bool; no failed action may be retried on PartialFailure. Never treat Rejected as a partial payment; compare clock before/after when debugging. The enum is about **time application**, not an inventory/action success contract. Other assets cannot write the clock's bFaulted. Full rollback is not promised.
Check creation, display labels and enum pin in UE 5.8.4.