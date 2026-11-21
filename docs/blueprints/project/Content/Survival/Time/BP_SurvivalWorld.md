# BP_SurvivalWorld — единый clock и диспетчер шагов

**Mirror:** `docs/blueprints/project/Content/Survival/Time/BP_SurvivalWorld.md` → **real project target:** `<ProjectRoot>/Content/Survival/Time/BP_SurvivalWorld.uasset`.
**Builder:** Claude Code + Unreal MCP в открытом UE 5.8.4; прежде чем запускать, проверять доступные MCP-операции и [Epic Blueprint API 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI). Это не `.uasset`.
**Контроль:** compile/save/inspect actual nodes + указанная ниже проверка; затем обновление [build backlog](../../../BACKLOG.md) в ветке Claude, если были расхождения.
**Статус: `stencil drafted`, 21.11.2026.** Это инструкция для реального Blueprint; в UE ещё не собиралось, названия пинов проверить в версии 5.8.4. Один файл = один Blueprint.

```text
Package: /Game/Survival/Time/BP_SurvivalWorld
AssetType: Blueprint Class
ParentClass: Actor
DependsOn: ST_SimStep, BPI_SimStepReceiver, Gameplay Tags settings
PlacedIn: /Game/Maps/Tests/L_F00_TimeLab (ровно 1 instance)
```

## Почему именно он первый

Все действия (идти, искать, разбирать, топить, спать) будут платить **одному** владельцу времени. Он не знает экономику ресурсов и баланс физиологии. Системы получают один и тот же интервал в **порядке фаз**, а не обмениваются Event Tick. Без этого переход к F01/F02 даст двойное начисление времени или разные температуры одной ночи.

## Пошаговая сборка в редакторе UE 5.8.4

1. Создать `/Game/Survival/Time/` и ассеты `ST_SimStep`, `BPI_SimStepReceiver` по собственным трафаретам. Project Settings → Gameplay Tags → Manage Gameplay Tags: добавить `Time.Advance.Debug`, `Time.Advance.Realtime`, `Time.Advance.Action`, `Time.Advance.Sleep`.
2. Content Browser → Blueprint Class → Actor → `BP_SurvivalWorld`. Compile/Save.
3. В Class Defaults: выключить `Start with Tick Enabled`. **Event Tick не реализовывать.**
4. Создать переменные и функции ниже; затем Graph; Compile/Save.
5. Создать пустой уровень `L_F00_TimeLab` в `/Game/Maps/Tests/`. Разместить **один** экземпляр `BP_SurvivalWorld`. Уровень — отдельный `.umap`, не Blueprint и не обязан иметь собственный stencil.

## Variables

| Name | UE type | Default | Writer | Persistence / usage |
|---|---|---:|---|---|
| `InitialWorldSeconds` | Double | `28800.0` | Level designer (config) | старт 08:00 от начала сценария, не save |
| `WorldTimeSeconds` | Double | `0.0` | **только BP_SurvivalWorld** | authoritative runtime, persist via SaveGame |
| `FixedStepSeconds` | Double | `900.0` | Class Defaults (config) | <= 15 игровых минут, provisional, не баланс |
| `bIsAdvancing` | Boolean | false | только BP_SurvivalWorld | runtime guard, **не save** |
| `Participants` | Array of Object references | empty | Register/Unregister functions | runtime references, **не save** |

Объекты в `Participants` должны реализовывать `BPI_SimStepReceiver` (это могут быть Actor или ActorComponent). Массив не хранит копий состояний тела/комнаты.

## Function / event contracts

```text
GetWorldTimeSeconds() -> Value: Double

RegisterParticipant(Participant: Object) -> bRegistered: Boolean
UnregisterParticipant(Participant: Object) -> bRemoved: Boolean

AdvanceGameTime(DeltaGameSeconds: Double, Reason: GameplayTag)
    -> bAccepted: Boolean

RestoreWorldTime(RestoredSeconds: Double) -> bRestored: Boolean

Dispatcher OnTimeAdvanceFinished(NewTimeSeconds: Double, Reason: GameplayTag)
```

## Event graph — точный порядок execution

```text
event BeginPlay() {
    Set WorldTimeSeconds = InitialWorldSeconds
    Set bIsAdvancing = false
    // Test level has no automatic realtime clock.
}

function RegisterParticipant(Participant:Object) -> bRegistered {
    if (bIsAdvancing || NOT IsValid(Participant)) return false
    if (NOT DoesImplementInterface(Participant, BPI_SimStepReceiver)) return false
    if (Participants.Contains(Participant)) return false
    Participants.AddUnique(Participant)
    return true
}

function UnregisterParticipant(Participant:Object) -> bRemoved {
    if (bIsAdvancing) return false
    return Participants.RemoveItem(Participant) // true if removed
}

function GetWorldTimeSeconds() -> Value:Double {
    return WorldTimeSeconds
}

function RestoreWorldTime(RestoredSeconds:Double) -> bRestored {
    if (bIsAdvancing || RestoredSeconds < 0) return false
    WorldTimeSeconds = RestoredSeconds
    return true      // NEVER call SimulateStep during restore
}

function AdvanceGameTime(DeltaGameSeconds:Double, Reason:GameplayTag) -> bAccepted {
    if (bIsAdvancing) return false
    if (FixedStepSeconds <= 0) return false
    if (DeltaGameSeconds <= 0 || DeltaGameSeconds > 86400) return false
    // One call can advance at most a day. Larger jumps are a series of calls.

    bIsAdvancing = true
    let Remaining:Double = DeltaGameSeconds
    let N:Int = CeilToInt(DeltaGameSeconds / FixedStepSeconds)

    for (Index in 0 .. N-1) {
        let StepDelta:Double = Min(Remaining, FixedStepSeconds)
        let Start:Double = WorldTimeSeconds
        let End:Double = Start + StepDelta

        let Step:ST_SimStep = MakeST_SimStep(
            StartSeconds=Start, EndSeconds=End,
            DeltaSeconds=StepDelta, Reason=Reason)
        Set WorldTimeSeconds = End

        for (Phase in 0 .. 4) {
            for (Participant in Participants) {
                if (IsValid(Participant)
                    && DoesImplementInterface(Participant, BPI_SimStepReceiver)) {
                    let ActualPhase:Int = GetSimPhase (Message, Target=Participant)
                    if (ActualPhase == Phase) {
                        SimulateStep (Message, Target=Participant, Step=Step)
                    }
                }
            }
        }
        Set Remaining = Remaining - StepDelta
    }

    Set bIsAdvancing = false
    Call OnTimeAdvanceFinished(NewTimeSeconds=WorldTimeSeconds, Reason=Reason)
    return true
}
```

`CeilToInt`, `Min`, `For Loop`, `Make ST_SimStep`, `Does Implement Interface`, `Add Unique` и Interface Message искать как штатные Blueprint nodes. Если подпись узла или pin отличается в редакторе, **зафиксировать фактическое имя/путь и поправить трафарет**, а не придумывать реализацию на глаз. Это логическая схема соединений, не копируемый код.

Время передаётся `SimulateStep` после установки clock на `EndSeconds`. Сам receiver обязан использовать **интервал Step**, а не вычислять новый elapsed из GetWorldTime. `OnTimeAdvanceFinished` — только UI, логи или test reporting, **не физика**.

### Фазы, будущая совместимость

```text
0 BPC_Climate         → внешние условия шага
1 BPC_HeatSource      → оплаченные дрова и тепловой поток
2 BPC_RoomThermal     → тепло комнаты/щели/укрытие
3 BPC_SurvivalBody    → реакция тела на реально обновлённую среду
4 future needs        → накопленные hunger/thirst/fatigue и т. п.
```

Отдельный `BPC_TimeActionRunner` в F04 будет **просить этот clock** об AdvanceGameTime, но сам не хранит `WorldTimeSeconds`. Пауза обычного realtime во время длительной операции — ответственность общего mode/controller, а не второй независимой шкалы. Нельзя пользоваться `Set Global Time Dilation` вместо честной оплаты 8 часов сна.

### Отложенный Save/Load контракт

`SG_TheLull` должен сохранять `WorldTimeSeconds` (Double). При Load: восстановить authoritative snapshots мира и участников; затем `RestoreWorldTime(SavedSeconds)` **без** `SimulateStep`. После восстановления зарегистрировать активных участников и только тогда снова пропускать время. Сам `SG_TheLull` пока **не создан** и его наличие нельзя заявлять.

## Проверка в PIE (обязательна до `asset assembled` → `PIE tested`)

1. Собрать `BP_F00ClockProbe` по отдельному трафарету, запустить тестовый уровень.
2. Два запуска с одинаковым 08:00: `AdvanceGameTime(3600)` против четырёх `AdvanceGameTime(900)`. В обоих `WorldTimeSeconds=32400`, `TotalReceivedSeconds=3600`, `StepCallCount=4`.
3. `AdvanceGameTime(-60)` → false, часы и probe неизменны; повторная регистрация одного участника не создаёт повторного вызова.
4. Если receiver попытается вызвать `AdvanceGameTime` внутри `SimulateStep`, вложенный вызов отвергается (bIsAdvancing). В тестовом probe это можно проверить позднее без добавления такого поведения в production.
5. `RestoreWorldTime(28800)` НЕ вызывает `SimulateStep`, не расходует ресурс.

**Предел первой итерации:** поддерживается только single-player и честный game clock; нет автоматически текущего времени, тела, погоды, печи или SaveGame. Не выдавать за F05 core loop.

## Проверенные первоисточники / статус

- Epic UE 5.8: [Blueprint Classes](https://dev.epicgames.com/documentation/en-us/unreal-engine/creating-blueprint-classes-in-unreal-engine), [Actor ticking](https://dev.epicgames.com/documentation/unreal-engine/actor-ticking-in-unreal-engine), [Blueprint Interfaces](https://dev.epicgames.com/documentation/unreal-engine/blueprints-visual-scripting-editor-user-interface-for-blueprint-interfaces-in-unreal-engine).
- Hoarbound (фактическая реализация, не copy-paste): [SimulationClock](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/time/simulation_clock.gd), [TimeCostedActionSystem](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/actions/time_costed_action_system.gd).
- Приоритет игры и исследование: [Survival Manifest](../../../../../gameplay/SURVIVAL_MANIFEST.md), [F00 foundation](../../../../../gameplay/reference/SURVIVAL_FOUNDATION_00_TO_UE.md).
- **Проверено:** чтение документации и контрактов. **Не проверено:** реальная компиляция этого Blueprint, взаимодействие с .uasset и поведение PIE.
