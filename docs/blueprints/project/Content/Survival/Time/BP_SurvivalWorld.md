# BP_SurvivalWorld — единый clock и dispatcher

Package: /Game/Survival/Time/BP_SurvivalWorld
AssetType: Blueprint Class
Mirror: `docs/blueprints/project/Content/Survival/Time/BP_SurvivalWorld.md` → `<ProjectRoot>/Content/Survival/Time/BP_SurvivalWorld.uasset`.
**Статус: revised draft, 21.11.2026; NEEDS RE-REVIEW.** Не создан в UE. Точный тип/пин и операции MCP подтвердить локально в UE 5.8.4; [backlog](../../../BACKLOG.md). Ревью [Claude Cloud #3](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969).

ParentClass: Actor
DependsOn: ST_SimStep, E_SimPhase, BPI_SimStepReceiver, Gameplay Tags settings
PlacedIn: /Game/Maps/L_KeyWestBlockout (1 instance, persistent level, no runtime spawn in F00).

## Создание
Собрать зависимости сначала. Blueprint Class → Actor. Start with Tick Enabled=false; нет Event Tick. Разместить один экземпляр в persistent level. Все clock writers ниже — **функции**, не Custom Events в общем графе. Actor BeginPlay не назначает время: уровень вызывает явный InitializeNewGame, а при загрузке вместо него вызывается RestoreWorldTime. До начала F05 SaveGame не существует, тест восстановления пользуется явным вызовом. Нет автоматического реального времени в F00.

## Variables
Все runtime variables Private=true, Instance Editable=false, Expose on Spawn=false, Replication=None; ни один не выставляется наружу. `WorldTimeSeconds` — читать через getter. Не помечать SaveGame этого actor как замену будущему SG_TheLull.
| Name | UE type | Default | Meaning |
|---|---|---|---|
| InitialWorldSeconds | Float (double precision) | 28800.0 | Private class default, 08:00 |
| WorldTimeSeconds | Float (double precision) | 0.0 | authoritative seconds, valid only when bReady |
| bReady | Boolean | false | explicit initialization gate |
| bIsAdvancing | Boolean | false | dispatch + finished callback guard |
| bIsRegistering | Boolean | false | reentry guard around GetSimPhase |
| Participants | Object Reference Array | empty | registration order |
| ParticipantPhases | Map<Object Reference, E_SimPhase> | empty | cached phase per registered object |

Fixed step cap is literal 900.0 Float (double precision); no editable zero/tiny value. Supported time range 0..1e9 seconds (provisional F00 contract, ~31.7 simulated years), max one advance 86400 seconds. For delta that cannot be represented at current time reject before mutation; comparison bounds reject NaN/infinite. These are technical limits not gameplay balance. 
## Function / event contracts
```text
InitializeNewGame() -> bInitialized: Boolean
IsClockReady() -> bReady: Boolean
GetWorldTimeSeconds() -> Value: Float (double precision)
RegisterParticipant(Participant: Object Reference) -> bRegistered: Boolean
UnregisterParticipant(Participant: Object Reference) -> bRemoved: Boolean
AdvanceGameTime(DeltaGameSeconds: Float (double precision), Reason: Gameplay Tag) -> bAccepted: Boolean
RestoreWorldTime(RestoredSeconds: Float (double precision)) -> bRestored: Boolean
OnTimeAdvanceFinished(NewTimeSeconds: Float (double precision), Reason: Gameplay Tag) // Event Dispatcher
```
GetWorldTimeSeconds and IsClockReady pure, others impure. Getter before ready returns 0; caller must check IsClockReady first. Helpers below Private functions. 
## Event graph
```text
event BeginPlay() {
    // No time write. No auto-initialize. No resetting flags here.
    CheckUniqueClock()
}
```
## Function graphs — execution spec
```text
function CheckUniqueClock() -> bUnique {
    let Found = GetAllActorsOfClass(BP_SurvivalWorld)
    if (Found.Length != 1) { PrintString("Clock: expected exactly one instance"); return false }
    return Found[0] == Self
}
function IsClockReady() -> bReady { return bReady }
function GetWorldTimeSeconds() -> Value { return WorldTimeSeconds }
function InitializeNewGame() -> bInitialized {
    if (bReady || bIsAdvancing || bIsRegistering) return Reject("already initialized or busy")
    if (NOT CheckUniqueClock()) return false
    if (NOT (InitialWorldSeconds >= 0.0 && InitialWorldSeconds <= 1000000000.0)) return Reject("invalid initial time")
    Set WorldTimeSeconds = InitialWorldSeconds
    Set bReady = true
    return true
}
function RestoreWorldTime(RestoredSeconds) -> bRestored {
    if (bIsAdvancing || bIsRegistering) return Reject("busy")
    if (NOT CheckUniqueClock()) return false
    if (NOT (RestoredSeconds >= 0.0 && RestoredSeconds <= 1000000000.0)) return Reject("invalid saved time")
    Set WorldTimeSeconds = RestoredSeconds
    Set bReady = true
    return true
}
function RegisterParticipant(Participant) -> bRegistered {
    if (NOT bReady || bIsAdvancing || bIsRegistering) return Reject("not ready or busy")
    if (NOT IsValid(Participant)) return Reject("invalid receiver")
    if (NOT DoesImplementInterface(Participant, BPI_SimStepReceiver)) return Reject("missing interface")
    if (Participants.Contains(Participant)) return Reject("duplicate receiver")
    Set bIsRegistering = true
    Set local CachedPhase = GetSimPhase(Message, Target=Participant)
    Set bIsRegistering = false
    if (NOT IsValid(Participant)) return Reject("receiver destroyed")
    if (NOT IsDispatchPhase(CachedPhase)) return Reject("unassigned/invalid phase")
    Participants.Add(Participant)
    ParticipantPhases.Add(Participant, CachedPhase)
    return true
}
function UnregisterParticipant(Participant) -> bRemoved {
    if (bIsAdvancing || bIsRegistering) return Reject("busy")
    Set local Removed = Participants.RemoveItem(Participant)
    ParticipantPhases.Remove(Participant)
    return Removed
}
function AdvanceGameTime(DeltaGameSeconds, Reason) -> bAccepted {
    if (NOT bReady || bIsAdvancing || bIsRegistering) return Reject("not ready or busy")
    if (NOT CheckUniqueClock()) return false
    if (NOT (DeltaGameSeconds > 0.0 && DeltaGameSeconds <= 86400.0)) return Reject("invalid delta")
    if (NOT IsAllowedReason(Reason)) return Reject("invalid reason")
    Set local Target = WorldTimeSeconds + DeltaGameSeconds
    if (NOT (Target > WorldTimeSeconds && Target <= 1000000000.0)) return Reject("time range or resolution")
    PruneInvalidParticipants()
    Set bIsAdvancing = true
    for (Index in 0 .. 95) { // For Loop with Break
        if (WorldTimeSeconds >= Target) break
        Set local Start = WorldTimeSeconds
        Set local End = Min(Target, Start + 900.0)
        Set local Step = MakeST_SimStep(StartSeconds=Start, EndSeconds=End, Reason=Reason)
        Set WorldTimeSeconds = End
        for (Phase in [Climate, HeatSource, RoomThermal, Body, Needs]) {
            for (Participant in Participants) {
                if (IsValid(Participant)) {
                    Find ParticipantPhases[Participant] -> CachedPhase, Found
                    if (Found && CachedPhase == Phase) SimulateStep(Message, Target=Participant, Step=Step)
                }
            }
        }
    }
    // Completed from For Loop with Break (both exhausted and early break)
    PruneInvalidParticipants() // private helper, no external callbacks
    if (WorldTimeSeconds != Target) {
        Set bIsAdvancing = false
        PrintString("Clock FATAL: step invariant broken; partial advance, stop session")
        return false
    }
    Broadcast OnTimeAdvanceFinished(WorldTimeSeconds, Reason) // guard stays true through listeners
    Set bIsAdvancing = false
    return true
}
```
**Helpers with exact behavior:** Reject(Message:String)->Boolean: Print String with prefix Clock and return false. IsDispatchPhase(Phase:E_SimPhase)->Boolean: equality/OR of five named phases, excludes sentinel/invalid. IsAllowedReason(Reason:GameplayTag)->Boolean: Is Gameplay Tag Valid then exact equality to four configured leaf tags; no parent match. PruneInvalidParticipants(): iterate array indexes descending (ForLoop on 0..Length-1 with reverse index computed from initial length); for invalid object remove Map key and Array index; if array empty return. Map Find output Found checked. Map and array never exposed. After pruning rebuild cache from surviving entries if removal of invalid object key is not reliable in actual UE; do not call GetSimPhase again. Validate actual Map key behavior before handoff. In F00 no dynamic destruction/creation during callbacks; if an object nevertheless becomes invalid it is skipped then pruned, not invoked. EndPlay receivers unregister; busy rejection is logged, next prune removes invalid objects. CheckUniqueClock at initialization/restore/advance, before any time mutation. F00 clock never spawned/despawned during callback; future streaming changes require new ownership review. 
**Blueprint translation:** each Set local = once evaluated on exec chain, especially phase message and bounds; named list via Make Array of E_SimPhase literals and For Each Loop, no integer → enum cast. Nested loops use Completed correctly; break only outer loop; guard cleared on every exit after set. Engine nodes/pins and Map key support need Local verification; do not assume text parser compiles.
**Restore contract:** allowed before initialization and in an idle clock. It does not dispatch or send OnTimeAdvanceFinished. Future load coordinator suspends all time requests and restores all owner snapshots together; no runtime save/load yet. InitializeNewGame subsequently refuses and never erases loaded time. 
**Partition limit:** F00 guarantees exact elapsed clock and equal four 900-second intervals for 3600 vs 4×900. Different arbitrary call partitions can give different receiver integration steps; no claim of identical climate/body outcome. F01 must verify integration sensitivity and define step policy; no rounding away paid time.
## PIE acceptance
See BP_F00ClockProbe. Reject before ready/duplicate world/invalid delta/reason/range; test restore-first then init (must reject), explicit restore after advance (no replay); nested Advance and Restore rejected; duplicate receiver rejected; cached phase tested; zero/negative steps never emitted; final target reached. External variable setter must not be accessible from another BP; inspect Private flags. Tests for two simultaneous clocks and phase ordering are in probe contract. No actual UE result yet.
## Source verification
- [Epic LWC, served as UE 5.8](https://dev.epicgames.com/documentation/tr-tr/unreal-engine/large-world-coordinates-in-unreal-engine-5): Blueprint Float has single/double precision subtypes.
- [Epic Blueprint Variables, served as 5.9](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine): Float type and Private property; exact 5.8.4 editor labels and MCP pin encoding still require local inspection.
- [Epic UE 5.8 Enum authoring](https://dev.epicgames.com/documentation/unreal-engine/designer-02-create-a-key-in-unreal-engine).
- [Epic UE 5.8 Get All Actors Of Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Actor/GetAllActorsOfClass), [Is Gameplay Tag Valid](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GameplayTags/IsGameplayTagValid).

Blueprint interface behavior and function graphs: [Epic Blueprint Interface](https://dev.epicgames.com/documentation/unreal-engine/blueprint-interface-in-unreal-engine?lang=en-US) (served 5.9; local 5.8.4 check required). [F00 foundation](../../../../../gameplay/reference/SURVIVAL_FOUNDATION_00_TO_UE.md).
