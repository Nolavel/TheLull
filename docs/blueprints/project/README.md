# TheLull — текстовое зеркало UE-проекта для сборки через Claude Code + Unreal MCP

**Статус:** только схема сборки. Это **не** локальный Unreal-проект и не копия `.uasset`/`.umap`. Реальный `.uproject` и существующие ассеты пока не проверены. Версия редактора проекта: **UE 5.8.4**; справка Epic — **UE 5.8**.

**Процедура:** [`../README.md`](../README.md). **Обязательный фильтр каждого изменения:** [`../../gameplay/SURVIVAL_MANIFEST.md`](../../gameplay/SURVIVAL_MANIFEST.md). **Результаты и улучшения после сборки:** [`BACKLOG.md`](BACKLOG.md).

## Правило соответствия путей

Корнем зеркала считаем **эту папку** `docs/blueprints/project/`. Вложенные имена совпадают с путями **внутри установленного проекта UE**, но расширение заменено на `.md` и содержимое — контракт. Пример:

```text
docs/blueprints/project/Content/Survival/Time/BP_SurvivalWorld.md
                                  ↓ Claude Code + Unreal MCP
<ProjectRoot>/Content/Survival/Time/BP_SurvivalWorld.uasset
                                  ↔ Package /Game/Survival/Time/BP_SurvivalWorld
```

**Нельзя** копировать Markdown из зеркала в настоящий `Content/` вместо ассета или объявлять mirror рабочим Unreal-проектом. Папки проекта, которым пока не соответствует ни одного реального нужного действия (`Plugins`, `Source`, `Saved`, `Intermediate`), **не создаём ради полноты дерева**. `Source` не нужен Blueprint-only эксперименту. `<ProjectRoot>` определяется через реально открытый `.uproject`, а не догадкой по пути.

## Дерево уже запланированных объектов F00

```text
project/
├── README.md                      ← этот индекс
├── BACKLOG.md                     ← журнал проверок и улучшений после сборки
├── Config/
│   └── DefaultGameplayTags.ini.md  → Config/DefaultGameplayTags.ini
└── Content/
    ├── Survival/
    │   └── Time/
    │       ├── ST_SimStep.md           → ST_SimStep.uasset
    │       ├── BPI_SimStepReceiver.md  → BPI_SimStepReceiver.uasset
    │       └── BP_SurvivalWorld.md     → BP_SurvivalWorld.uasset
    ├── Tests/
    │   └── Survival/
    │       └── BP_F00ClockProbe.md    → BP_F00ClockProbe.uasset
    └── Maps/
        └── Tests/
            └── L_F00_TimeLab.md       → L_F00_TimeLab.umap
```

Только **один целевой файл** на каждую MD-карточку. Общие планы и backlog в корне mirror **не являются** asset-трафаретами. Существует одна canonical-карточка на один package path.

## Очерёдность сборки (строго по зависимостям)

1. **Preflight:** Claude открывает локальный `.uproject`, подтверждает actual UE **5.8.4**, структуру `Content`/`Config`, ветку `ue-claudeflow` и список **доступных инструментов текущего Unreal MCP**. Если проект не доступен — BLOCKED, не притворяться, что редактор открыт.
2. **Config:** [`DefaultGameplayTags.ini.md`](Config/DefaultGameplayTags.ini.md); сначала прочитать оригинальный ini, затем добавлять только отсутствующие четыре тега, проверить в редакторе.
3. **Struct:** [`ST_SimStep.md`](Content/Survival/Time/ST_SimStep.md).
4. **Interface:** [`BPI_SimStepReceiver.md`](Content/Survival/Time/BPI_SimStepReceiver.md).
5. **Actor:** [`BP_SurvivalWorld.md`](Content/Survival/Time/BP_SurvivalWorld.md).
6. **Test Actor:** [`BP_F00ClockProbe.md`](Content/Tests/Survival/BP_F00ClockProbe.md).
7. **Test Level:** [`L_F00_TimeLab.md`](Content/Maps/Tests/L_F00_TimeLab.md).
8. **Inspection + PIE:** получить реальную структуру ассетов/графов, Compile, Save, PIE. Сопоставить **expected vs actual**. Пополнить [`BACKLOG.md`](BACKLOG.md) незафиксированными ошибками, слабостями паттерна и улучшениями. Только затем принимать следующий блок F01.

**Текущий реальный статус:** все шесть файлов — планы; их `.uasset`, `.umap`, `.ini` на машине автора через этот чат **не были созданы и не проверялись**. Наличие дерева GitHub не означает, что локальный проект содержит эти пути.

## Источники UE 5.8 (не заменять на «5.9 по памяти»)

- [Unreal Engine 5.8 Documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine)
- [Blueprint API Reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI)
- [Blueprint Class Assets](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-class-assets-in-unreal-engine)
- [Blueprints Visual Scripting](https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprints-visual-scripting-in-unreal-engine)
- [Scripting and Automating the Unreal Editor](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-and-automating-the-unreal-editor)
- [Using Gameplay Tags](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-gameplay-tags-in-unreal-engine)
- [Automation Test Framework](https://dev.epicgames.com/documentation/en-us/unreal-engine/automation-test-framework-in-unreal-engine)

Версия справочника Epic — **5.8**, а установленный hotfix проекта — **5.8.4**. Названия узлов, типов, pin и MCP-операций проверяются на фактически открытом редакторе **до сборки/приёмки**. Не использовать новые возможности 5.9, пока они не доказаны в 5.8.4.
