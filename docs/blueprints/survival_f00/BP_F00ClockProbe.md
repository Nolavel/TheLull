# BP_F00ClockProbe — временный PIE-тест clock
**Статус: `stencil drafted` (21.11.2026), не создан в UE.** Один файл — один Blueprint. Это test harness: в игровую карту TheLull не переносить.

```text
Package: /Game/Tests/Survival/BP_F00ClockProbe
AssetType: Blueprint Class
ParentClass: Actor
Implements: BPI_SimStepReceiver
DependsOn: ST_SimStep, BPI_SimStepReceiver, BP_SurvivalWorld, Gameplay Tag Time.Advance.Debug
PlacedIn: /Game/Maps/Tests/L_F00_TimeLab (ровно 1 instance)
```

## Собрать в UE 5.8.4
1. Content Browser → `/Game/Tests/Survival/` → Blueprint Class → Actor → `BP_F00ClockProbe`.
2. Class Settings → Implemented Interfaces → `BPI_SimStepReceiver`. Compile.
3. Поставить один instance рядом с `BP_SurvivalWorld` на `L_F00_TimeLab`.
4. Создать переменные/реализации ниже. `bSingleCall` сделать **Instance Editable**. Start with Tick Enabled = false; Event Tick не использовать.
5. Compile, Save, Play In Editor (PIE). Ожидается печать PASS/FAIL, но этот результат пока не снят.

## Variables
| Name | UE type | Default | Purpose |
|---|---|---|---|
| `bSingleCall` | Boolean | true | true: один час одним Advance; false: четыре раза по 15 мин |
| `Clock` | BP_SurvivalWorld Object Reference | None | найденный instance, read/call, **не владелец времени** |
| `StartSeconds` | Double | 0 | baseline для проверки |
| `TotalReceivedSeconds` | Double | 0 | сумма только фактически принятых шагов |
| `LastStepEndSeconds` | Double | 0 | последнее `Step.EndSeconds` |
| `StepCallCount` | Integer | 0 | число вызовов interface event |
| `bAccepted` | Boolean | false | результат последнего вызова; только тест |

## Event Graph

```text
event BeginPlay() {
    Delay(Duration=0.1) // ONLY test harness: allow all actors to finish BeginPlay
    let Found:Array<BP_SurvivalWorld> = GetAllActorsOfClass(BP_SurvivalWorld)
    if (Found.Length != 1) {
        PrintString(InString="F00 FAIL: expected exactly one BP_SurvivalWorld")
        return
    }
    Set Clock = Found[0]
    Set StartSeconds = Clock.GetWorldTimeSeconds()
    Set TotalReceivedSeconds = 0
    Set LastStepEndSeconds = StartSeconds
    Set StepCallCount = 0

    let Registered:Bool = Clock.RegisterParticipant(Self)
    if (NOT Registered) {
        PrintString(InString="F00 FAIL: cannot register probe")
        return
    }

    if (bSingleCall) {
        Set bAccepted = Clock.AdvanceGameTime(
            DeltaGameSeconds=3600.0, Reason=Time.Advance.Debug)
    } else {
        for (Index in 0 .. 3) {
            Set bAccepted = Clock.AdvanceGameTime(
                DeltaGameSeconds=900.0, Reason=Time.Advance.Debug)
        }
    }

    let FinalSeconds = Clock.GetWorldTimeSeconds()
    let Passed = bAccepted
        && NearlyEqual(FinalSeconds - StartSeconds, 3600.0)
        && NearlyEqual(TotalReceivedSeconds, 3600.0)
        && (StepCallCount == 4)
        && NearlyEqual(LastStepEndSeconds, FinalSeconds)

    PrintString(InString=FormatText(
        "F00 {Passed}: time={FinalSeconds}, accepted={bAccepted}, steps={StepCallCount}, received={TotalReceivedSeconds}"))
}

function GetSimPhase() -> Phase:Integer {
    return 3 // test receiver in body phase, without any physiology
}

event SimulateStep(Step:ST_SimStep) { // Interface event
    if (NOT NearlyEqual(Step.EndSeconds - Step.StartSeconds, Step.DeltaSeconds)) {
        PrintString(InString="F00 FAIL: malformed ST_SimStep")
    }
    Set TotalReceivedSeconds = TotalReceivedSeconds + Step.DeltaSeconds
    Set StepCallCount = StepCallCount + 1
    Set LastStepEndSeconds = Step.EndSeconds
}
```

`FormatText`, `NearlyEqual`, `GetAllActorsOfClass`, `Delay`, `ForLoop`, Print String — штатные Blueprint nodes; реальное имя и тип конкретного pin подтвердить в UE перед отметкой `asset assembled`. В actual Blueprint сборке условия `Passed` собрать логическими Boolean nodes, а форматирование — `Format Text`. **Это не исполняемый исходный код.**

## Проверка
1. PIE запуск c `bSingleCall=true` → `time=32400`, `steps=4`, `received=3600`, PASS.
2. Остановить PIE, установить `bSingleCall=false`; повторить → **те же числа**.
3. Отдельно вызвать `Clock.AdvanceGameTime(-60.0, Time.Advance.Debug)`: false, ничего не изменилось.
4. Вызвать `RegisterParticipant(Self)` второй раз: false, duplicate не добавлен.
5. Для теста загрузки позднее: `RestoreWorldTime(28800)` после прогона не должен увеличивать `StepCallCount`. В F00 нет `SG_TheLull`.

При ошибке зафиксировать фактический pin, ошибки компилятора и observed values в этот stencil либо рядом с PR; не чинить трафарет так, чтобы он утверждал несуществующую проверку.

**Проверено сейчас:** спроектирован тест двух разбиений одного часа. **Не проверено:** создание `.uasset`, компиляция, PIE. После проверки тестовый actor можно убрать из уровня, но оставить stencil для регрессии.
