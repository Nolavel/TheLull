# Трафарет проекта TheLull

[Манифест](../../gameplay/SURVIVAL_MANIFEST.md) · [Как собирать](../README.md) · [Backlog Claude](BACKLOG.md)

Это текстовое зеркало **только создаваемых или изменяемых файлов** реального UE-проекта. `project/` не является вторым .uproject. Markdown хранится отдельно от настоящих бинарных ассетов. В UE `Content/` — ассеты/карты, `Config/` — настройки. Наши вложенные `Survival/Time`, `Maps`, `Tests` — соглашение по назначению, а не требование UE. Не создавать папки без реальной необходимости.

## Сначала готовый шаблон Epic

UE 5.8.4 → Games → Third Person → Blueprint → Variant None. [Epic docs — выбрать 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine?application_version=5.8). Если локальный проект уже на шаблоне, сохранить существующие package paths (обычно `Content/ThirdPerson/`, `Content/Characters/`, input и level geometry). Имена сверить в открытом редакторе. Не дублировать готовые assets, не создавать на неизменённые файлы отдельные MD. Камеру/движение переработаем позже по реальным потребностям.

До готовности локального редактора Codex готовит трафареты, Claude Cloud исследует и проверяет инструменты. Local собирает их при фактическом запуске UE и ведёт backlog; Cloud может отдельно ревьюить переданные результаты. [Роли](../../../CLAUDE.md).

## Наши первые дополнения

```text
project/
├── Config/
│   └── DefaultGameplayTags.ini.md
└── Content/
    ├── Maps/
    │   └── L_KeyWestBlockout.md
    ├── Survival/
    │   └── Time/
    │       ├── ST_SimStep.md
    │       ├── BPI_SimStepReceiver.md
    │       └── BP_SurvivalWorld.md
    └── Tests/
        └── Survival/
            └── BP_F00ClockProbe.md
```

Пример: `project/Content/Maps/L_KeyWestBlockout.md` → `<ProjectRoot>/Content/Maps/L_KeyWestBlockout.umap` → `/Game/Maps/L_KeyWestBlockout`. Другие расширения .uasset и .ini соответственно. README/BACKLOG — служебные документы, не UE assets. Source/Plugins/Saved/Intermediate не создаём впрок. Любое изменение пути при обнаружении реального template согласуется, не плодит дублей.

## Порядок

1. **F−1**: preflight .uproject / UE 5.8.4 / template / реально доступные MCP operations.
2. **F−1**: [L_KeyWestBlockout](Content/Maps/L_KeyWestBlockout.md), улицы, несколько укрытий, 727 не главный shelter. Проверка географии PR #340, камеры и перемещения в PIE.
3. **F00**: [Config](Config/DefaultGameplayTags.ini.md) → [ST_SimStep](Content/Survival/Time/ST_SimStep.md) → [BPI_SimStepReceiver](Content/Survival/Time/BPI_SimStepReceiver.md) → [BP_SurvivalWorld](Content/Survival/Time/BP_SurvivalWorld.md) → [BP_F00ClockProbe](Content/Tests/Survival/BP_F00ClockProbe.md). Подключаем к той же карте; probe opt-in. Пустая TimeLab не нужна.
4. После каждого asset Claude Local через MCP: build → Compile/Save → inspect → PIE → actual vs stencil → [BACKLOG](BACKLOG.md) → handoff Codex. Дальше F01 и последующие связи на этой карте.

Официальная документация [UE 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine?application_version=5.8) и [Blueprint API](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI?application_version=5.8): проверить версию в селекторе, пины и возможности в установленной 5.8.4. **Ни один из наших ассетов ещё не создан и PIE не проверялся.**
