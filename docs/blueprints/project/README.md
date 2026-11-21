# Трафарет проекта TheLull

[Манифест](../../gameplay/SURVIVAL_MANIFEST.md) · [Как собирать](../README.md) · [Backlog Claude](BACKLOG.md)

Это текстовое зеркало **только создаваемых или изменяемых файлов** реального UE-проекта. `project/` не является вторым .uproject. Markdown хранится отдельно от настоящих бинарных ассетов. В UE `Content/` — ассеты/карты, `Config/` — настройки. Наши вложенные `Survival/Time`, `Maps`, `Tests` — соглашение по назначению, а не требование UE. Не создавать папки без реальной необходимости.

## Сначала готовый шаблон Epic

UE 5.8.4 → Games → Third Person → Blueprint → Variant None. [Epic docs — выбрать 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine?application_version=5.8). Если локальный проект уже на шаблоне, сохранить существующие package paths (обычно `Content/ThirdPerson/`, `Content/Characters/`, input и level geometry). Имена сверить в открытом редакторе. Не дублировать готовые assets, не создавать на неизменённые файлы отдельные MD. Камеру/движение переработаем позже по реальным потребностям.

Автор подтвердил 21.11.2026: **UE 5.8.4 уже установлен локально; Unreal MCP ещё не настроен, UE-проект ещё не создан.** Это сообщение автора, не результат инспекции редактора. Codex готовит трафареты, Claude Cloud заранее перепроверяет их (SHA, конкретные замечания, исправления, непроверяемое локально); Codex исправляет, Local настраивает MCP, создаёт проект и забирает согласованные трафареты для сборки и backlog. Позднее Cloud может отдельно ревьюить полученные результаты. [Роли](../../../CLAUDE.md).

**Статус F00, 21.11.2026:** исправленный пакет из `ue-codex@1b15f38c4978167bb6e6f8a3fd190ba6cf31100b` опубликован в production как **revised draft / NEEDS RE-REVIEW**, не как готовое задание на сборку. Claude Cloud подтвердил исправление десяти замечаний, но полное повторное инженерное ревью каждого MD не завершено. Никаких UE-ассетов, Compile/PIE этим переносом не получено. Local может готовить окружение независимо; сборка конкретного трафарета — после его ревью и проверки MCP.

## Наши первые дополнения

```text
project/
├── Config/
│   ├── DefaultGameplayTags.ini.md
│   └── DefaultEngine.ini.md
└── Content/
    ├── Maps/
    │   ├── L_SurvivalCore.md
    │   └── L_KeyWestBlockout.md (deferred)
    ├── Survival/
    │   ├── Environment/
    │   │   ├── BP_CoreExposureZone.md
    │   │   └── BP_CoreRestSpot.md
    │   ├── Actions/
    │   │   ├── ST_CoreSupplies.md
    │   │   └── BPC_CoreActions.md
    │   ├── Body/
    │   │   ├── ST_CoreVitals.md
    │   │   └── BPC_SurvivalBody.md
    │   └── Time/
    │       ├── E_SimPhase.md
    │       ├── E_AdvanceResult.md
    │       ├── ST_SimStep.md
    │       ├── BPI_SimStepReceiver.md
    │       └── BP_SurvivalWorld.md
    ├── UI/Survival/
    │   ├── WBP_VitalsHUD.md
    │   └── WBP_SurvivalDebug.md
    └── Tests/
        └── Survival/
            └── BP_F00ClockProbe.md
```

Пример: `project/Content/Maps/L_KeyWestBlockout.md` → `<ProjectRoot>/Content/Maps/L_KeyWestBlockout.umap` → `/Game/Maps/L_KeyWestBlockout`. Другие расширения .uasset и .ini соответственно. README/BACKLOG — служебные документы, не UE assets. Source/Plugins/Saved/Intermediate не создаём впрок. Любое изменение пути при обнаружении реального template согласуется, не плодит дублей.

## Ближайшая локальная сессия (вторник, 24.11.2026)

Приоритет автора — настройка, не обещание готовой механики. Claude Local: создать Third Person Blueprint (None) проект, проверить UE 5.8.4 и реальные MCP capabilities; открыть штатный уровень, выполнить базовый PIE, записать доступные операции и блокировки. Если останутся время и подходящий проверенный stencil, выполнить один малый полный цикл: `E_SimPhase` — создание/Save/reopen + сверка значений (сам Enum не имеет PIE), затем при доступности зависимостей минимальное использование в BP/PIE. Не считать сохранение Enum доказательством поведения clock. Допустимо закончить сессию на настройке среды. После этого F00 и Core на штатном уровне. География не требуется.

**Уточнение автора 21.11.2026 (заменяет прежний порядок):** сначала ядро survival по The Long Dark, затем минимальный UI и Debug UI с рабочими индикаторами; география только после этого. Штатная Third Person площадка нужна для запуска, не реконструкция квартала. Key West не отменён, но не является зависимостью core. Первичные F01/F02 используют контролируемый температурный вход, полная климатическая модель позднее.
До локального запуска: предметный core, HUD, Debug. Географию не начинать.

[Dependency audit](DEPENDENCY_AUDIT.md) — read before Cloud review. Config/DefaultEngine.ini is modified only after the real L_SurvivalCore map exists.

## Порядок

**Разрешение автора 21.11.2026:** Codex может целевыми коммитами публиковать подготовленные survival MD-трафареты и их документы в `production` ДО независимого ревью, с явным статусом `NEEDS REVIEW` / `NEEDS RE-REVIEW` и указанием snapshot/зависимостей. Это не разрешение на произвольный merge ветки, перенос lab/CI или изменение чужой ветки. Local не считает такие MD готовыми к сборке до Cloud review и проверки реального MCP.

1. **F−1**: Claude Local настраивает MCP, создаёт Third Person Blueprint project (Variant None), подтверждает .uproject / установленный UE 5.8.4 / template / реально доступные MCP operations. Перед сборкой — результат предварительного ревью Cloud по SHA трафарета.
2. **F−1**: [L_SurvivalCore](Content/Maps/L_SurvivalCore.md), копия штатного уровня, не район.
3. **F00**: [Config](Config/DefaultGameplayTags.ini.md) → [E_SimPhase](Content/Survival/Time/E_SimPhase.md) + [E_AdvanceResult](Content/Survival/Time/E_AdvanceResult.md) + [ST_SimStep](Content/Survival/Time/ST_SimStep.md) → [BPI_SimStepReceiver](Content/Survival/Time/BPI_SimStepReceiver.md) → [BP_SurvivalWorld](Content/Survival/Time/BP_SurvivalWorld.md) → [BP_F00ClockProbe](Content/Tests/Survival/BP_F00ClockProbe.md). Подключаем к L_SurvivalCore; probe opt-in.
4. После каждого asset Claude Local через MCP: build → Compile/Save → inspect → PIE → actual vs stencil → [BACKLOG](BACKLOG.md) → handoff Codex. Дальше [BP_CoreExposureZone](Content/Survival/Environment/BP_CoreExposureZone.md) + [ST_CoreVitals](Content/Survival/Body/ST_CoreVitals.md) → [BPC_SurvivalBody](Content/Survival/Body/BPC_SurvivalBody.md) → [HUD](Content/UI/Survival/WBP_VitalsHUD.md) → [Debug](Content/UI/Survival/WBP_SurvivalDebug.md). Next add [ST_CoreSupplies](Content/Survival/Actions/ST_CoreSupplies.md), [BP_CoreRestSpot](Content/Survival/Environment/BP_CoreRestSpot.md), [BPC_CoreActions](Content/Survival/Actions/BPC_CoreActions.md), then integrate Paid J/K/L in Debug+Level. География после рабочего ядра.

Официальная документация [UE 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine?application_version=5.8) и [Blueprint API](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI?application_version=5.8): проверить версию в селекторе, пины и возможности в установленной 5.8.4. **Ни один из наших ассетов ещё не создан и PIE не проверялся.** F00 revised after Cloud #3; re-review pending. Новый уровень размещения, core и UI — NEEDS REVIEW; F00 graph не менялся.
