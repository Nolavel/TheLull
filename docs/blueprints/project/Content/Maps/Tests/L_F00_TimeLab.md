# L_F00_TimeLab — карта для первого PIE smoke

**Mirror:** `docs/blueprints/project/Content/Maps/Tests/L_F00_TimeLab.md` → **real target:** `<ProjectRoot>/Content/Maps/Tests/L_F00_TimeLab.umap`.
**Тип:** один Unreal level asset (карта, не Blueprint). **Статус:** planned, не создавалась.

## Создание через Claude Code + Unreal MCP
1. В UE 5.8.4 проверить: карта ещё не существует, уровень `L_F00_TimeLab` не является текущей рабочей картой. Не перезаписывать существующий `.umap`.
2. Создать Blank Level в `/Game/Maps/Tests/L_F00_TimeLab`, сохранить.
3. Разместить **один** instance `BP_SurvivalWorld`, package `/Game/Survival/Time/BP_SurvivalWorld`; и **один** `BP_F00ClockProbe`, package `/Game/Tests/Survival/BP_F00ClockProbe`. Не переносить probe в production level.
4. Запустить PIE; выполнить оба сценария из [BP_F00ClockProbe.md](../../Tests/Survival/BP_F00ClockProbe.md) (3600 sec once и 4×900 sec). При отсутствии MCP-операций размещения/PIE — зафиксировать BLOCKED и конкретный недоступный шаг.
5. Compile + Save assets + map, inspect, собирать журнал фактического результата в backlog. Проверить что в проекте не появилось лишних дублей /Game/SurvivalWorld.

**Минимальный expected:** старт 08:00 (28800 seconds), результат 09:00 (32400), 4 шага симуляции, 3600 полученных секунд. Нет визуального UI и погодной/телесной симуляции: это F00, не весь core-loop.

**Источники Epic 5.8:** [Automation Test Framework](https://dev.epicgames.com/documentation/en-us/unreal-engine/automation-test-framework-in-unreal-engine), [Blueprint Class Assets](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-class-assets-in-unreal-engine).
