# BPI_SimStepReceiver — интерфейс участника времени

Package: /Game/Survival/Time/BPI_SimStepReceiver
AssetType: Blueprint Interface
Mirror: `docs/blueprints/project/Content/Survival/Time/BPI_SimStepReceiver.md` → `<ProjectRoot>/Content/Survival/Time/BPI_SimStepReceiver.uasset`.
**Статус: revised draft, 21.11.2026; NEEDS RE-REVIEW.** Не создан в UE. Точный тип/пин и операции MCP подтвердить локально в UE 5.8.4; [backlog](../../../BACKLOG.md). Ревью [Claude Cloud #3](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969).

DependsOn: ST_SimStep, E_SimPhase.
## Signatures
```text
GetSimPhase() -> Phase: E_SimPhase
SimulateStep(Step: ST_SimStep) -> (no output)
```
Создать Blueprint Interface, не Actor. GetSimPhase реализуется функцией с output, возвращает выбранную фазу без побочных эффектов. Clock опрашивает ровно один раз при успешной регистрации, сохраняет результат; смена фазы через unregister/register **между** AdvanceGameTime, не во время вызова. Unassigned не принимается. SimulateStep без output реализуется Interface Event; вход Step by value; вызывающий uses Interface Message на Object после проверки Does Implement Interface и Is Valid. 
Порядок Climate → HeatSource → RoomThermal → Body → Needs; внутри одной фазы — порядок регистрации. Receiver делает только синхронное изменение своего состояния, без Delay/latent work, второго clock, spawn/destroy clock, изменения списка участников или вызовов Advance/Restore. На EndPlay владелец actor/component вызывает UnregisterParticipant, если Clock valid; невалидные ссылки чистит clock. 
## Проверка
Probe реализует GetSimPhase (Body), SimulateStep; за 3600 секунд при 900 s cap получает четыре интервала. Unassigned должен отклоняться. Ни одного Event Tick как замены SimulateStep.
- [Epic LWC, served as UE 5.8](https://dev.epicgames.com/documentation/tr-tr/unreal-engine/large-world-coordinates-in-unreal-engine-5): Blueprint Float has single/double precision subtypes.
- [Epic Blueprint Variables, served as 5.9](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine): Float type and Private property; exact 5.8.4 editor labels and MCP pin encoding still require local inspection.
- [Epic UE 5.8 Enum authoring](https://dev.epicgames.com/documentation/unreal-engine/designer-02-create-a-key-in-unreal-engine).
- [Epic UE 5.8 Get All Actors Of Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Actor/GetAllActorsOfClass), [Is Gameplay Tag Valid](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GameplayTags/IsGameplayTagValid).
