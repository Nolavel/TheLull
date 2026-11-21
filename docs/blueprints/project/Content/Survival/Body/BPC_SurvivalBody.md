# BPC_SurvivalBody — first vitals

Package: /Game/Survival/Body/BPC_SurvivalBody
AssetType: Blueprint Class
DependsOn: ST_CoreVitals, ST_SimStep, BPI_SimStepReceiver, E_SimPhase, BP_SurvivalWorld, BP_CoreExposureZone; these are all custom asset stencils (see DEPENDENCY_AUDIT.md).
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

ParentClass: ActorComponent
Implements: BPI_SimStepReceiver
 
Owner: player pawn; one instance added by core level harness. Component Tick disabled. No auto reset in BeginPlay. Private variables (not editable/exposed): Vitals (ST_CoreVitals default), Clock (BP_SurvivalWorld Object Reference None), bInitialized (Boolean false), ExposureZone (BP_CoreExposureZone Object Reference None), bOverrideExposure (Boolean false), OverrideFeelsLikeC (Float double precision; -10.0), bCoreResting (Boolean; false).
 
## Functions / pins
```text
InitializeFixture(InClock: BP_SurvivalWorld Object Reference, InZone: BP_CoreExposureZone Object Reference) -> bOK:Boolean
GetVitals() -> Snapshot:ST_CoreVitals (pure, by value)
GetSimPhase() -> Phase:E_SimPhase
SetFixtureExposure(FeelsLikeC: Float(double precision)) -> bOK:Boolean
ClearFixtureExposureOverride() -> bOK:Boolean
ApplyFixtureReplenish(RestAdd01, HydrationAdd01, HungerAdd01: Float(double precision)) -> bOK:Boolean
ApplyPaidRecovery(RestAdd01, HydrationAdd01, HungerAdd01: Float(double precision)) -> bApplied:Boolean
SetCoreResting(bNewResting:Boolean) -> bOK:Boolean
SimulateStep(Step:ST_SimStep) -> bApplied:Boolean
OnVitalsChanged(Snapshot:ST_CoreVitals) // Event Dispatcher
```
InitializeFixture: reject if initialized, invalid clock, zone or !IsClockReady; Set Clock + ExposureZone, RegisterParticipant(Self); on false clear references and return false; set initialized true, query initial exposure via ResolveExposure, update FeelsLikeC/ExposureSource, broadcast Vitals, return true. Spawn outside Box for fresh regression. Phase function always Body. GetVitals returns copy. Inputs accepted only after init, if Clock.IsSimulationFaulted=false, Clock.IsTimeDispatching=false and Clock.IsClockReady=true; test map calls only while clock idle/manual. Every public fixture writer validates these preconditions BEFORE touching any field. Exposure bounds -50..50; additions each 0..1; reject out-of-bounds/nonfinite (positive range comparisons). Set Members in copy then Set Vitals once. For SetFixtureExposure set bOverrideExposure=true and OverrideFeelsLikeC from input, update FeelsLikeC/ExposureSource via ResolveExposure, deltas/hours zero; LastCause="Fixture exposure override". ClearFixtureExposureOverride sets false, refreshes from zone, zeros deltas/hours, broadcasts once; no time/needs change. In manual mode outside these commands the location input is sampled on next clock step, not continuously. Replenish independently Clamp(old+add,0,1); report actual deltas, zero other deltas/hours; LastCause="Fixture replenish". No time write, no health refill. Publish once per accepted operation. Test-only API remains separate from real paid effects. ApplyPaidRecovery is a controlled effect endpoint, called only by BPC_CoreActions after Clock returned Completed: validate all additions 0..1 finite, at least one positive; clock initialized/ready/idle/not faulted; update only Rest01/Hydration01/Hunger01 clamped, zero other diagnostics, set LastStepHours=0 and LastCause="Paid resource effect", broadcast once, return true only after Vitals written. NO clock advancement inside ApplyPaidRecovery. An unexpected false after paid time is a terminal ACTION fault, not rollback. SetCoreResting(true) requires ready/idle/nonfaulted, toggles only bCoreResting and never adjusts Rest directly. SetCoreResting(false) permits cleanup after clock failure when no longer dispatching; must not require Clock.IsSimulationFaulted=false. The caller cannot change flag during dispatch. This action contract does not mean consumption by debug mock keys.
 
## Event graph
```text
function SimulateStep(Step) -> bApplied:Boolean {
    if (NOT bInitialized) return false
    return ApplyStep(Step)
}
event EndPlay(EndPlayReason) {
    if (IsValid(Clock)) Clock.UnregisterParticipant(Self)
}
```
## Function graphs
Synthetic test coefficients, not medical or TLD balance: all rates game points/hour.
```text
function ApplyStep(Step) -> bApplied:Boolean {
    let H = (Step.EndSeconds - Step.StartSeconds)/3600.0
    if (NOT (H > 0 && H <= 0.25)) { PrintString("invalid body step"); return false }
    let Old = Vitals
    let Exposure, Source = ResolveExposure()
    if (Source == "Invalid zone fallback") { PrintString("Core FATAL: zone input invalid"); return false }
    let RW = Clamp(Exposure*0.04,-1,1)
    let W = Clamp(Old.Warmth01+RW*H,0,1)
    let RR = (bCoreResting ? 0.20 : -0.06)  // synthetic signed Rest rate per game hour
    let R = Clamp(Old.Rest01+RR*H,0,1)
    let T = Clamp(Old.Hydration01-0.08*H,0,1)
    let F = Clamp(Old.Hunger01-0.05*H,0,1)
    let Loss = 0.20*EmptyHours(Old.Warmth01,RW,H)
             + 0.03*EmptyHours(Old.Rest01,RR,H)
             + 0.08*EmptyHours(Old.Hydration01,-0.08,H)
             + 0.04*EmptyHours(Old.Hunger01,-0.05,H)
    let C = Clamp(Old.Condition01-Loss,0,1)
    Set Vitals = MakeST_CoreVitals(
      Warmth01=W,Rest01=R,Hydration01=T,Hunger01=F,Condition01=C,
      FeelsLikeC=Exposure,ExposureSource=Source,WarmthDelta=W-Old.Warmth01,
      RestDelta=R-Old.Rest01,HydrationDelta=T-Old.Hydration01,
      HungerDelta=F-Old.Hunger01,ConditionDelta=C-Old.Condition01,
      LastStepHours=H,LastCause=(bCoreResting ? "Rest step" : "Clock step"))
    Broadcast OnVitalsChanged(Vitals)
    return true
}
function ResolveExposure() -> FeelsLikeC, Source {
    if (bOverrideExposure) return (OverrideFeelsLikeC,"DEBUG override")
    if (NOT IsValid(ExposureZone)) return (-10.0,"Invalid zone fallback")
    let C, Inside, Valid = ExposureZone.QueryExposure(GetOwner())
    if (NOT Valid) return (-10.0,"Invalid zone fallback")
    if (Inside) return (C,"Zone inside")
    return (C,"Zone outside")
}
function EmptyHours(Start01, SignedRatePerHour, Hours) -> Value {
    if (SignedRatePerHour < 0) return Clamp(Hours-Start01/(-SignedRatePerHour),0,Hours)
    if (SignedRatePerHour == 0 && Start01 == 0) return Hours
    return 0
}
```
ApplyStep private impure, returns false before any body mutation when prevalidation fails. ResolveExposure and EmptyHours private pure; all numeric locals/inputs double precision. Actual pin names and interface event implementation verify. No passive Condition recovery yet. Rest action is one 900 game-second slice, not whole-night sleep. Inventory and interruption policy remain future contracts. Future climate replaces zone provider; no second clock/body bar. Save later restores five raw fields and does not replay step.
## Acceptance
Fresh fixture 1 game h at -10: W=.6 R=.94 T=.92 F=.95 C=1. At 3h total W=0 C=.9 (only after empty). +5 for next hour W=.2 C=.9 (no recovery yet). Equal one hour vs four quarter hours at fixed input, within 1e−5. Debug replenish affects only chosen need, not clock. Spatial test (override cleared): from partially depleted warmth, walk across Box boundary and advance 900 game seconds. Inside gain +0.05, outside loss −0.10 while within bar limits; other needs drain equally. Debug source changes after the step. Invalid zone fallback must be conspicuously labeled and logged in local review; not shipping behavior. External setter inaccessible. Additional acceptance: after 1h awake, one 900s Rest inside spot and protected zone raises Rest01 by +0.05 (0.20/h), reduces Hydration01 by 0.02 and Hunger01 by 0.0125, and updates Warmth from zone. Paid Drink/Eat uses ApplyPaidRecovery only after clock Completed; debug mock stays free but explicitly separate. PIE NOT RUN.
