# BPC_CoreActions — finite paid needs actions (first playable choice)

Package: /Game/Survival/Actions/BPC_CoreActions
AssetType: Blueprint Class
ParentClass: ActorComponent
DependsOn: /Game/Survival/Actions/ST_CoreSupplies, /Game/Survival/Body/BPC_SurvivalBody, /Game/Survival/Time/BP_SurvivalWorld, /Game/Survival/Time/E_AdvanceResult, /Game/Survival/Environment/BP_CoreRestSpot, /Game/Survival/Environment/BP_CoreExposureZone, Config/DefaultGameplayTags.ini
Status: NEEDS REVIEW / NOT ASSEMBLED / NOT PIE TESTED. 21.11.2026.
Owners: only this component changes finite WaterServings and FoodServings; only Body changes needs; only Clock changes game time. No Tick, no latent actions, no extra game timer.

## Why this exists
First genuine causal choice before geography: drink a **finite** portion; eat a **finite** portion; or rest at a spatially valid spot. All choices charge the **same clock** and the needs continue evolving while time passes. Key design property: no replenishment without both a successful paid action and stock debit. Current debug keys 5/6/7 still do free MOCK replenishment and must be marked distinct; these gameplay functions must NEVER call ApplyFixtureReplenish.

Source distinction:
- Official Hinterland status page confirms Warmth/Fatigue/Thirst/Hunger + Condition; game-design inference: food/water/rest link needs with cost.
- Hoarbound main hydration/hunger/fatigue components keep independent stocks and test sleep/one clock; implementation is not copied.
- **All game coefficients below are fixture tuning**, not Hinterland formulas or physiological claims.

## Private state
| Name | UE type | Default |
|---|---|---|
| Clock | BP_SurvivalWorld Object Reference | None |
| Body | BPC_SurvivalBody Object Reference | None |
| Zone | BP_CoreExposureZone Object Reference | None |
| RestSpot | BP_CoreRestSpot Object Reference | None |
| Supplies | ST_CoreSupplies | struct default (0,0,"Uninitialized") |
| bInitialized | Boolean | false |
| bActionActive | Boolean | false |
| bActionFaulted | Boolean | false |
| LastActionError | String | "" |

Runtime values all Private=true, not Instance Editable, not replicated. Attach once to the stock Player Pawn by L_SurvivalCore after Body. Initialize once; Level/actors read stock only via getters. Do not create full Inventory/ItemCatalog yet.

## Public Blueprint functions / exact outputs
- InitializeCoreActions(InClock:BP_SurvivalWorld Object Reference, InBody:BPC_SurvivalBody Object Reference, InZone:BP_CoreExposureZone Object Reference, InRestSpot:BP_CoreRestSpot Object Reference) -> bOK:Boolean (impure).
- GetStock() -> Snapshot:ST_CoreSupplies (pure, by value).
- IsActionFaulted() -> bFaulted:Boolean (pure).
- GetLastActionError() -> Message:String (pure).
- TryDrink() -> TimeResult:E_AdvanceResult, bCommitted:Boolean (impure).
- TryEat() -> TimeResult:E_AdvanceResult, bCommitted:Boolean (impure).
- TryRest15m() -> TimeResult:E_AdvanceResult, bCommitted:Boolean (impure).
- OnSuppliesChanged(Snapshot:ST_CoreSupplies) Event Dispatcher.
- OnCoreActionFinished(TimeResult:E_AdvanceResult, bCommitted:Boolean, Message:String) Event Dispatcher, only once per attempted action after validation/commit handling.

InitializeCoreActions validates all refs, Clock.IsClockReady, NOT Clock.IsTimeDispatching/IsSimulationFaulted, GetOwner==Body.GetOwner, exactly one component on pawn. If okay seed Supplies=(2,1,"Initial fixture stock"), save refs, bInitialized=true, fire OnSuppliesChanged once. Reject duplicate init without resetting stock. Do not unregister with clock: this component is NOT a BPI receiver.

## Shared preflight before any requested action
Reject with (Rejected,false) and specific LastActionError if bInitialized false, bActionActive, bActionFaulted, invalid references, clock not ready/dispatching/faulted, or stock/need/location prerequisite fails. Neither clock time nor stock/needs changes. Set bActionActive=true on acceptance before calling clock. End every branch with bActionActive=false and OnCoreActionFinished, but never hide PartialFailure.

Because BP_SurvivalWorld does not provide transactions, **all post-advance effects must be locally guaranteed by preflight**. If a post-advance Body recovery unexpectedly fails, set bActionFaulted=true, log "ACTION FATAL paid time without effect", return (Completed,false), and let the level stop further test actions and automatic timer. Do NOT claim clock rolled back or that its own bFaulted changed. bCommitted means *every promised post-advance effect happened*. No retries after an action fault.

## TryDrink graph (one pressed key = one attempt)
1. Validate WaterServings>=1 and Body.GetVitals().Hydration01<0.99, plus shared preflight.
2. Clock.AdvanceGameTime(60.0, Time.Advance.Action). This interval is in **game seconds**.
3. If result != Completed, do NOT spend stock or refill. On PartialFailure set bActionFaulted=true; emit result + error; do not retry.
4. If Completed, call Body.ApplyPaidRecovery(RestAdd01=0, HydrationAdd01=0.35, HungerAdd01=0) **once**. This is valid only outside time dispatch, after Clock returns.
5. If applied=true: Set Supplies.WaterServings=old−1, LastStockChange="Drank one finite serving"; broadcast OnSuppliesChanged; return (Completed,true).
6. If applied=false: latch action failure as above, return (Completed,false). Any consumed time is real and cannot be replayed.

## TryEat graph
Same structure, FoodServings>=1 and Hunger01<0.99, Clock.AdvanceGameTime(120.0, Time.Advance.Action), Body.ApplyPaidRecovery(0,0,0.35), then stock FoodServings-=1 only on successful Body commit. On failure preserve stock and report. No physical nutrition realism claimed.

## TryRest15m graph
Validate Rest01<0.99; RestSpot.CanRest(GetOwner)==true; Zone.QueryExposure(GetOwner) reports Valid=true and Inside=true; Body and clock ready. Set bActionActive=true. Call Body.SetCoreResting(true) while clock idle; if false reject without time. Call Clock.AdvanceGameTime(900.0, Time.Advance.Sleep). Body advances its Rest need with **resting rate +0.20 / game hour** during this slice, other needs/temperature continue changing. Once Advance returns, call Body.SetCoreResting(false) even when time partially failed (cleanup allowed when clock faulted and no longer dispatching). Return (Completed,true) only if both Advance completed and rest flag cleared. If PartialFailure or cleanup failure, bActionFaulted=true and report (actual TimeResult, false). No artificial free RestAdd after Advance.

Intentional scope: one 15-minute rest slice, cancellable by *not requesting the next slice*. A full sleeping/night manager, interruptions inside a long duration, save/wake and Condition recovery are separate future contracts. Do not pretend this quarter-hour fixture implements a night.

## Local PIE acceptance (not run)
At freshly initialized stock 2 water / 1 food: pressing Drink when thirst full returns Rejected without spending **time or stock**. After a paid 3600 s interval, TryDrink charges exactly +60 s, decreases water count to 1, increases hydration by actual +0.35 minus the 60 s drain (clamp at 1); trying with zero stock returns Rejected/no time debit. TryEat charges +120 s and eats exactly one food portion. Rest outside spot rejects without time debit; inside protected zone AND rest box charges 900 s and raises Rest01 by +0.05 for 15 game minutes, while thirst and hunger drop. Action result distinguishes (Completed,true) from (Completed,false) terminal fault and PartialFailure. Verify no duplicate events, no double-paid time, stock numbers in Debug, and stock surviving multiple action attempts within same PIE. Not SaveGame persistence yet.
