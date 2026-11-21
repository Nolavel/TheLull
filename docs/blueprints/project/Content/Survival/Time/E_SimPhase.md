# E_SimPhase — порядок получателей шага

Package: /Game/Survival/Time/E_SimPhase
AssetType: Blueprint Enumeration
Mirror: `docs/blueprints/project/Content/Survival/Time/E_SimPhase.md` → `<ProjectRoot>/Content/Survival/Time/E_SimPhase.uasset`.
**Статус: revised draft, 21.11.2026; NEEDS RE-REVIEW.** Не создан в UE. Точный тип/пин и операции MCP подтвердить локально в UE 5.8.4; [backlog](../../../BACKLOG.md). Ревью [Claude Cloud #3](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969).

## Создание
Content Browser → Add → Blueprint → Enumeration. Имя E_SimPhase. Добавить в указанном порядке:
```text
Unassigned
Climate
HeatSource
RoomThermal
Body
Needs
```
Unassigned — sentinel, не dispatch phase, default для нового receiver; не добавлять MAX вручную. Порядок выполнения задаётся явным массивом именованных значений в BP_SurvivalWorld, не числовой конверсией enum. Save; убедиться, что BPI GetSimPhase имеет именно этот enum pin. Пробный receiver с Unassigned отвергается (см. probe). Не переименовывать/переставлять значения без проверки зависимостей.
- [Epic LWC, served as UE 5.8](https://dev.epicgames.com/documentation/tr-tr/unreal-engine/large-world-coordinates-in-unreal-engine-5): Blueprint Float has single/double precision subtypes.
- [Epic Blueprint Variables, served as 5.9](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine): Float type and Private property; exact 5.8.4 editor labels and MCP pin encoding still require local inspection.
- [Epic UE 5.8 Enum authoring](https://dev.epicgames.com/documentation/unreal-engine/designer-02-create-a-key-in-unreal-engine).
- [Epic UE 5.8 Get All Actors Of Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Actor/GetAllActorsOfClass), [Is Gameplay Tag Valid](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GameplayTags/IsGameplayTagValid).
