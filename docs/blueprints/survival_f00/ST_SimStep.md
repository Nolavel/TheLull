# ST_SimStep — интервал симуляции
Статус: `stencil drafted` (21.11.2026). Не создан в редакторе и не проверен PIE.
**Один файл — один UE asset.**

- `Package: /Game/Survival/Time/ST_SimStep`
- `AssetType: Blueprint Structure (User Defined Struct)`
- `ParentClass: —`
- `DependsOn: Gameplay Tags settings`
- `OwnedBy: BP_SurvivalWorld` — только clock составляет фактический шаг.

## Создать в UE 5.8.4
1. Content Browser → `/Game/Survival/Time` (создать папку).
2. Add → Blueprints → Structure → `ST_SimStep`.
3. Добавить поля, ниже. Save. Никаких графов у Structure нет.

## Variables / fields
| Field | UE type | Default | Unit / rules |
|---|---|---|---|
| `StartSeconds` | Double | 0.0 | game seconds since scenario epoch |
| `EndSeconds` | Double | 0.0 | game seconds, >= StartSeconds |
| `DeltaSeconds` | Double | 0.0 | game seconds, exactly End - Start |
| `Reason` | Gameplay Tag | None | `Time.Advance.Realtime`, `Time.Advance.Action`, `Time.Advance.Sleep`, `Time.Advance.Debug` |

`ST_SimStep` — **передаваемая копия данных шага**, не владелец состояния и не save-slot. Не суммировать его во второй clock. Никакого печного топлива, здоровья или погоды здесь.

## Контракт интеграции
Писатель: `BP_SurvivalWorld.AdvanceGameTime`. Читатели: любые `BPI_SimStepReceiver` (строго через упорядоченный вызов clock). У receiver нет права менять интервал или запускать вложенный `AdvanceGameTime`.

## Проверка
- Structure компилируется и доступен как pin `Step` в `BPI_SimStepReceiver`.
- Разность `EndSeconds - StartSeconds` равна `DeltaSeconds` в проверке `BP_F00ClockProbe`.
- Статус сейчас: **draft only; UE not tested**.
