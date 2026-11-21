# BP_F00ClockProbe — opt-in PIE regression

Package: /Game/Tests/Survival/BP_F00ClockProbe
AssetType: Blueprint Class
Mirror: `docs/blueprints/project/Content/Tests/Survival/BP_F00ClockProbe.md` → `<ProjectRoot>/Content/Tests/Survival/BP_F00ClockProbe.uasset`.
**Статус: revised draft, 21.11.2026; NEEDS RE-REVIEW.** Не создан в UE. Точный тип/пин и операции MCP подтвердить локально в UE 5.8.4; [backlog](../../../BACKLOG.md). Ревью [Claude Cloud #3](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969).

ParentClass: Actor
Implements: BPI_SimStepReceiver
DependsOn: ST_SimStep, E_SimPhase, E_AdvanceResult, BPI_SimStepReceiver, BP_SurvivalWorld, Gameplay Tags
PlacedIn: L_SurvivalCore (one instance, bRunProbe=false normally).
## Variables
| Name | UE type | Default |
|---|---|---|
| bRunProbe | Boolean | false |
| bSingleCall | Boolean | true |
| bRestoreFirst | Boolean | false |
| bExpectDuplicateClock | Boolean | false |
| Clock | BP_SurvivalWorld Object Reference | None |
| Phase | E_SimPhase | Unassigned |
| StartSeconds | Float (double precision) | 0.0 |
| TotalReceivedSeconds | Float (double precision) | 0.0 |
| LastStepEndSeconds | Float (double precision) | 0.0 |
| StepCallCount | Integer | 0 |
| PhaseReadCount | Integer | 0 |
| bPassed | Boolean | true |


Only first four flags Instance Editable; other variables private. Tick off. Map Level Blueprint skips initialization only when exactly one opt-in probe exists; probe then owns test startup (see level).
## Event graph
```text
event BeginPlay() {
    if (NOT bRunProbe) return
    Delay(0.1) // test only; no production initialization depends on delay
    Set local Probes = GetAllActorsOfClass(BP_F00ClockProbe)
    Set local ActiveCount = 0
    for (P in Probes) { if (IsValid(P) && P.bRunProbe) ActiveCount += 1 }
    if (ActiveCount != 1) { PrintString("F00 FAIL: exactly one active probe required"); return }
    RunChecks()
}
event EndPlay(EndPlayReason) {
    if (IsValid(Clock)) Clock.UnregisterParticipant(Self)
}
function SimulateStep(Step:ST_SimStep) -> bApplied:Boolean {
    Set local Delta = Step.EndSeconds - Step.StartSeconds
    if (NOT (Delta > 0.0 && Delta <= 900.0 && NearlyEqual(Step.StartSeconds, LastStepEndSeconds, 0.00001))) { Set bPassed = false; return false }
    Check(Delta > 0.0 && Delta <= 900.0 && NearlyEqual(Step.StartSeconds, LastStepEndSeconds, 0.00001), "step positive, bounded, contiguous")
    Set TotalReceivedSeconds = TotalReceivedSeconds + Delta
    Set LastStepEndSeconds = Step.EndSeconds
    Set StepCallCount = StepCallCount + 1
    if (StepCallCount == 1) {
        Check(Clock.AdvanceGameTime(1.0, Time.Advance.Debug) == Rejected, "nested advance rejected")
        Check(NOT Clock.RestoreWorldTime(0.0), "nested restore rejected")
    }
    return bPassed
}
```
## Function graphs
```text
function GetSimPhase() -> Phase:E_SimPhase {
    Set PhaseReadCount = PhaseReadCount + 1 // TEST ONLY instrumentation; production receiver must be side-effect free
    return Phase
}
function Check(Condition:Boolean, Label:String) {
    if (NOT Condition) { Set bPassed = false; PrintString("F00 FAIL: " + Label) }
}
function RunChecks() {
    Set local Found = GetAllActorsOfClass(BP_SurvivalWorld)
    if (bExpectDuplicateClock) {
        Check(Found.Length == 2, "duplicate fixture")
        for (C in Found) {
            if (IsValid(C)) {
                Check(NOT C.InitializeNewGame(), "duplicate init rejected")
                Check(NOT C.RestoreWorldTime(28800.0), "duplicate restore rejected")
                Check(C.AdvanceGameTime(900.0, Time.Advance.Debug) == Rejected, "duplicate advance rejected")
                Check(NOT C.IsClockReady(), "duplicate remains unready")
            }
        }
        PrintResult()
        return
    }
    if (Found.Length != 1) { Check(false, "expected one clock"); PrintResult(); return }
    Set Clock = Found[0]
    Check(NOT Clock.IsClockReady(), "before init unready")
    Check(Clock.AdvanceGameTime(900.0, Time.Advance.Debug) == Rejected, "advance before init rejected")
    if (bRestoreFirst) {
        Check(Clock.RestoreWorldTime(43200.0), "restore before initialize")
        Check(NOT Clock.InitializeNewGame(), "new game cannot overwrite load")
        Check(Clock.GetWorldTimeSeconds() == 43200.0, "restored time retained")
    } else {
        Check(Clock.InitializeNewGame(), "explicit initialize")
        Check(Clock.GetWorldTimeSeconds() == 28800.0, "new game 08:00")
    }
    if (NOT Clock.IsClockReady()) { Check(false, "clock unready"); PrintResult(); return }
    Set StartSeconds = Clock.GetWorldTimeSeconds()
    Set LastStepEndSeconds = StartSeconds
    Set Phase = Unassigned
    Check(NOT Clock.RegisterParticipant(Self), "unassigned phase rejected")
    Set Phase = Body
    Check(Clock.RegisterParticipant(Self), "register once")
    Check(NOT Clock.RegisterParticipant(Self), "duplicate rejected")
    Check(PhaseReadCount == 2, "one query per attempted new registration, duplicate skipped")
    Set Phase = Climate // cache must remain Body; counts may not change
    Check(Clock.AdvanceGameTime(0.0, Time.Advance.Debug) == Rejected, "zero rejected")
    Check(Clock.AdvanceGameTime(-60.0, Time.Advance.Debug) == Rejected, "negative rejected")
    Check(Clock.AdvanceGameTime(86401.0, Time.Advance.Debug) == Rejected, "oversize rejected")
    Check(Clock.AdvanceGameTime(900.0, None) == Rejected, "invalid reason rejected")
    Check(Clock.GetWorldTimeSeconds() == StartSeconds && StepCallCount == 0, "invalid requests unchanged")
    if (bSingleCall) {
        Check(Clock.AdvanceGameTime(3600.0, Time.Advance.Debug) == Completed, "one hour accepted")
    } else {
        for (I in 0..3) Check(Clock.AdvanceGameTime(900.0, Time.Advance.Debug) == Completed, "quarter hour accepted")
    }
    Check(Clock.GetWorldTimeSeconds() == StartSeconds + 3600.0, "target reached")
    PrintString(FormatText("F00 hour: start={StartSeconds}, final={Clock.GetWorldTimeSeconds()}, calls={StepCallCount}, total={TotalReceivedSeconds}"))
    Check(StepCallCount == 4 && NearlyEqual(TotalReceivedSeconds,3600.0,0.00001), "four intervals")
    Check(PhaseReadCount == 2, "phase not re-queried during dispatch")
    Check(Clock.AdvanceGameTime(900.25, Time.Advance.Debug) == Completed, "fractional tail")
    Check(StepCallCount == 6 && NearlyEqual(TotalReceivedSeconds,4500.25,0.00001), "positive fractional tail not lost")
    Check(NOT Clock.RestoreWorldTime(28800.0), "restore after init rejected")
    Check(Clock.GetWorldTimeSeconds() == StartSeconds + 4500.25 && StepCallCount == 6, "post-init restore unchanged")
    Check(Clock.UnregisterParticipant(Self), "unregister")
    Check(Clock.AdvanceGameTime(900.0, Time.Advance.Debug) == Completed, "advance without receiver")
    Check(StepCallCount == 6, "no event after unregister")
    PrintResult()
}
function PrintResult() {
    if (bPassed) PrintString("F00 PASS")
    else PrintString("F00 FAIL: see individual checks")
}
```
For local variables inside Event Graph use private temporary members (ActiveCount/Probes/Delta) or move non-latent logic into a helper function; function-local variables are only in functions, not Event Graph. bRunProbe is public Instance Editable (other actor reads it). Each impure call executes once (store Boolean local then Check), not as a pretend pure expression. NearlyEqual = Float double precision with explicit tolerance 0.00001; verify actual node. Check latches failure forever for this run; no later PASS overrides failure. PhaseReadCount increment is probe-only diagnostics, not production behavior. 
## Runs / evidence
1. Fresh PIE bRunProbe=true, bSingleCall=true; repeated fresh PIE false; both final hour after initial phase +3600, four callbacks before tail. 
2. Fresh PIE bRestoreFirst=true; 43200 preserved, new game rejected, then +3600; no load replay. After success RestoreWorldTime returns false without changing clock.
3. Temporary second clock placed in test map; bExpectDuplicateClock=true: both reject init/restore/advance; remove duplicate after test.
4. Manual separate phase-order fixture using temporary additional test receivers implementing same BPI (or duplicate probe actors with bRunProbe=false and manually register by a temporary test graph, set phases via debugger before registration): register Body then Climate, advance one step, record actual callbacks in order Climate→Body, inspect cache unchanged. This is explicitly NOT covered by single receiver automated check; actual fixture/PIE evidence required before claiming phase order. Test invalidated reference pruning similarly with destroyed temporary receiver between advances. External accessor inspection: cannot Set WorldTimeSeconds on another actor. 
5. Temporary second active probe: both must print FAIL and neither initialize clock. Remove extra active probe.
6. Normal PIE bRunProbe=false: Level Blueprint initializes exactly once, no test advances. Remove probe before release or leave disabled in test map only. 
- [Epic LWC, served as UE 5.8](https://dev.epicgames.com/documentation/tr-tr/unreal-engine/large-world-coordinates-in-unreal-engine-5): Blueprint Float has single/double precision subtypes.
- [Epic Blueprint Variables, served as 5.9](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine): Float type and Private property; exact 5.8.4 editor labels and MCP pin encoding still require local inspection.
- [Epic UE 5.8 Enum authoring](https://dev.epicgames.com/documentation/unreal-engine/designer-02-create-a-key-in-unreal-engine).
- [Epic UE 5.8 Get All Actors Of Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Actor/GetAllActorsOfClass), [Is Gameplay Tag Valid](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GameplayTags/IsGameplayTagValid).

Поправка авторского порядка: изменён уровень размещения; F00 graph без изменений. Re-review остаётся открытым.

**Failure fixture for later PIE (not claimed automated):** one receiver purposely returns bApplied=false on a selected step; expected AdvanceGameTime=PartialFailure, bFaulted=true, no Finished broadcast, no further advance even if retried. Observe that world time and some participants may already have changed. Record exact point of failure in logs. Do not fake failure using an unrelated test assertion that itself returns false accidentally.
