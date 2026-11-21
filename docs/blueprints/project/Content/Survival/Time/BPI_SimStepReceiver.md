# BPI_SimStepReceiver — интерфейс участника времени

**Mirror:** `docs/blueprints/project/Content/Survival/Time/BPI_SimStepReceiver.md` → **real project target:** `<ProjectRoot>/Content/Survival/Time/BPI_SimStepReceiver.uasset`.
**Builder:** Claude Code + Unreal MCP в открытом UE 5.8.4; прежде чем запускать, проверять доступные MCP-операции и [Epic Blueprint API 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI). Это не `.uasset`.
**Контроль:** compile/save/inspect actual nodes + указанная ниже проверка; затем обновление [build backlog](../../../BACKLOG.md) в ветке Claude, если были расхождения.
Статус: `stencil drafted` (21.11.2026). Не создан/не компилировался в UE.
**Один файл — один UE asset.**

- `Package: /Game/Survival/Time/BPI_SimStepReceiver`
- `AssetType: Blueprint Interface`
- `ParentClass: Interface`
- `DependsOn: /Game/Survival/Time/ST_SimStep`

## Создать в UE 5.8.4
1. Content Browser → Add → Blueprints → Blueprint Interface, имя `BPI_SimStepReceiver`.
2. Добавить только две интерфейсные функции; реализацию/состояние внутрь interface не писать.
3. Скомпилировать. Actor/ActorComponent receiver добавляет interface через Class Settings → Implemented Interfaces.

## Functions / signatures
```text
GetSimPhase() -> Phase: Integer
SimulateStep(Step: ST_SimStep) -> (no output)
```

В Unreal `SimulateStep` без выходов может отображаться у реализующего класса как Event; вызывающий использует **Interface Message** на Object. `GetSimPhase` имеет выход и реализуется как функция.

## Семантика phase
- `0` — climate (environment inputs);
- `1` — heat source / finite fuel consumption;
- `2` — room thermal / shelter;
- `3` — body (температура и т. п.);
- `4` — прочие нужды, зависящие от результата предыдущих фаз.

Один receiver имеет **одну фазу**. При равной фазе вызываются в порядке регистрации; внутри одной фазы нельзя создавать причинную зависимость, которая требует обратного порядка. Нужна новая причинная связь — уточнить phase/контракт, а не поставить Tick.

## Writer / readers / persistence
Interface сам ничего не хранит. Источник мира — `BP_SurvivalWorld`. Каждый receiver меняет **только своё** authoritative состояние по данному `Step`. Save/Load отдельно восстанавливает snapshots и не воспроизводит уже оплаченные шаги.

## Ограничения
- Нельзя использовать `Event Tick` каждого receiver как замену `SimulateStep`.
- Нельзя из `SimulateStep` двигать `WorldTimeSeconds` или самопроизвольно вызывать `AdvanceGameTime`.
- Unreal не обещает нужный порядок Tick отдельных Actor: порядок задаёт clock явными вызовами.
- Не пересоздавать второй экземпляр интерфейса в другом домене.

## Проверка
`BP_F00ClockProbe` реализует обе функции и получает ровно четыре вызова по 900 game seconds за один час. Статус: **draft only; UE not tested**.
