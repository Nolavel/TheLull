# ST_SimStep — интервал симуляции

Package: /Game/Survival/Time/ST_SimStep
AssetType: Blueprint Structure (User Defined Struct)
Mirror: `docs/blueprints/project/Content/Survival/Time/ST_SimStep.md` → `<ProjectRoot>/Content/Survival/Time/ST_SimStep.uasset`.
**Статус: revised draft, 21.11.2026; NEEDS RE-REVIEW.** Не создан в UE. Точный тип/пин и операции MCP подтвердить локально в UE 5.8.4; [backlog](../../../BACKLOG.md). Ревью [Claude Cloud #3](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969).

DependsOn: Config/DefaultGameplayTags.ini. Consumers: BPI_SimStepReceiver, BP_SurvivalWorld, BPC_SurvivalBody, BP_F00ClockProbe.
OwnedBy: BP_SurvivalWorld — единственный создатель авторитетного интервала.

## Создание и fields
Add → Blueprints → Structure. Save.
| Field | UE type | Default | Unit |
|---|---|---|---|
| StartSeconds | Float (double precision) | 0.0 | game seconds since scenario epoch |
| EndSeconds | Float (double precision) | 0.0 | game seconds, > StartSeconds for dispatched step |
| Reason | Gameplay Tag | None | one of four Time.Advance.* leaf tags |

Убираем DeltaSeconds: каждый receiver вычисляет `EndSeconds - StartSeconds` как Float (double precision). Нет третьего независимо изменяемого числа. При передаче Step — значение (не by-reference). Default struct является только незаполненным значением, не допустимым интервалом.
Clock передаёт строго положительный интервал и разрешённый Reason. Receiver не пишет время, не запускает следующий шаг и не хранит второй clock.
## Проверка
Структура сохраняется, доступна в BPI/Make/Break ST_SimStep; actual field type/precision проверить. Probe проверяет положительность и непрерывность интервала и суммарную оплату. 
- [Epic LWC, served as UE 5.8](https://dev.epicgames.com/documentation/tr-tr/unreal-engine/large-world-coordinates-in-unreal-engine-5): Blueprint Float has single/double precision subtypes.
- [Epic Blueprint Variables, served as 5.9](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine): Float type and Private property; exact 5.8.4 editor labels and MCP pin encoding still require local inspection.
- [Epic UE 5.8 Enum authoring](https://dev.epicgames.com/documentation/unreal-engine/designer-02-create-a-key-in-unreal-engine).
- [Epic UE 5.8 Get All Actors Of Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Actor/GetAllActorsOfClass), [Is Gameplay Tag Valid](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GameplayTags/IsGameplayTagValid).
