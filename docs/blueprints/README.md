# Трафареты Blueprint

Трафарет — это **атомарная Markdown-спецификация одного будущего ассета или конфигурационного файла Unreal**. Codex пишет её в GitHub, локальный Claude Code создаёт asset через подключённый Unreal MCP в открытом UE 5.8.4 и сверяет результат с контрактом.

Зачем: облачная сторона не видит состояние локального редактора и не имеет права утверждать, что текст равен `.uasset`. Свободное описание («сделай ветвление по холоду») воспроизводится неоднозначно. Зафиксированные path, типы, pin, шаги графа и критерий проверки позволяют проверить фактическую сборку.

## Реальная цель библиотеки

**Это входной формат для локального Claude Code + Unreal MCP, а не инструкции автору вручную нарисовать граф.** Codex готовит точный атомарный MD, Claude Code строит и проверяет соответствующий реальный `.uasset`/`.umap`/`.ini` в открытом UE 5.8.4. Затем Claude записывает фактический diff и backlog, передаёт замечания Codex; автор разрешает спорные изменения и интеграцию.

Канон: [манифест survival](../gameplay/SURVIVAL_MANIFEST.md), [реалистичный F00](../gameplay/reference/SURVIVAL_FOUNDATION_00_TO_UE.md). Источник правильных API — [Epic UE 5.8 Documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine) и [Blueprint API 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI); для **установленной 5.8.4** дополнительно сверять реальные классы/пины в редакторе и список операций именно подключённого MCP. Не подставлять UE 5.9/UE6 и не придумывать MCP-actions.

## Дерево реального проекта, отражённое в Markdown

**Все новые трафареты** размещаем в [`project/`](project/README.md) с **той же вложенностью, что у будущего UE-проекта**:
- `project/Content/Survival/Time/BP_SurvivalWorld.md` → `<ProjectRoot>/Content/Survival/Time/BP_SurvivalWorld.uasset`;
- `project/Content/Maps/L_KeyWestBlockout.md` → `<ProjectRoot>/Content/Maps/L_KeyWestBlockout.umap`;
- `project/Config/DefaultGameplayTags.ini.md` → `<ProjectRoot>/Config/DefaultGameplayTags.ini`.

`project/` — **текстовое зеркало**, не отдельная собранная игра и не директория, которую нужно скопировать в Unreal `Content`. `<ProjectRoot>` Claude определяет по фактически открытому `.uproject`. Не создавать пустые `Source`, `Plugins`, `Saved`, `Intermediate` и фиктивный `.uproject`; добавляем путь только когда для него появился реальный asset/настройка.

[**Полный граф зависимостей**](project/DEPENDENCY_AUDIT.md) · [**Индекс сборки**](project/README.md): сначала F−1 — готовый Epic Third Person Template (Blueprint, None) и [L_SurvivalCore](project/Content/Maps/L_SurvivalCore.md); F00 Config → Enum + Struct → Interface → Clock → opt-in probe, Core → HUD → Debug → finite paid actions/RestSpot → Hoarbound 60-min normal day Driver + UE-native DayNightLighting (all unreviewed Blueprint stencils). Квартал позднее, 727 не главный shelter. Внутренние папки — наше соглашение, не обязательная структура UE; штатные ассеты не дублировать.

## Атомарный build + обратная связь

```text
Manifest + official Epic 5.8 + TLD/Hoarbound/Key West findings
                          ↓
Codex: one MD = one exact asset path + class + pins + graph + test
                          ↓ commit SHA of stencil
Claude Cloud: pre-build engineering review of exact stencil SHA → feedback to Codex → reviewed handoff
Claude Local: configure MCP + create Third Person project (UE 5.8.4 installed per owner)
Claude Local: preflight .uproject + installed UE 5.8.4 + actual Unreal MCP
                          ↓
one asset via MCP → Compile → Save → inspect actual nodes → PIE/automation
                          ↓
actual .uasset/.umap/.ini + logs + expected-vs-actual report
                          ↓
Claude Local: project/BACKLOG.md (in own ue-claudeflow branch)
                          ↓
Codex: update affected stencil in ue-codex after handoff
                          ↓
author approves integration → next asset / F01...
```

**После каждого asset, а не в конце проекта:** Claude Local сверяет все запланированные variables/types/defaults, node/pin links, parent, package, ownership/save, соседние контракты, компиляцию и реальные тесты. Проблема MCP, невозможность построения графа и неизвестные классы — явный `BLOCKED`, а не самодельная замена.

[**Журнал расхождений и улучшений (backlog)**](project/BACKLOG.md) содержит `Expected` vs `Actual`, доказательства из редактора, ссылки на docs UE 5.8, severity, проявление для core loop, решение и owner. Пока проверки не выполнены, все пункты `NOT RUN`. Claude **не редактирует ветку Codex**: результаты публикует в своей ветке, затем делает точный handoff. В `production` никто не сливает без решения автора.

Claude Cloud прежде всего проводит инженерное ревью MD до локальной сборки, указывает SHA, замечания, предложенные исправления и локально непроверенные вопросы; Codex исправляет трафареты. Cloud также готовит инструменты сверки и может ревьюить переданные артефакты после сборки; это не замена локальной самопроверке и backlog. UE 5.8.4 установлен по сообщению автора 21.11.2026; Local настраивает MCP и создаёт проект. В это время Codex готовит ближайшие зависимости, Cloud перепроверяет их до передачи Local. [Роли](../../CLAUDE.md).

Старый [`BP_LogicTest.md`](BP_LogicTest.md) остаётся историческим примером формата, **не частью F00**. Текущий `tools/check_stencil.py` способен сравнивать только `Event graph` Blueprint Class с текстовым выводом `uasset`, и **не** является универсальной проверкой Struct/Interface/Level/Config или доказательством PIE. Проверка по самому актуальному Unreal MCP/редактору обязательна; эвристика `rust-uasset` — дополнение.

## Формат

Для **Blueprint Class** использовать совместимый с `rust-uasset` синтаксис графа, но это **схема для воспроизведения через MCP**, а не сериализованный `.uasset`. Для Enum/Struct/Interface/Level/Config указывать целевой тип, точный путь и атомарный контракт без выдуманного Event Graph. У Class обязательны `Package`, `ParentClass`, `Variables`, функции/пины и `Event graph`.

- **Variables** — `имя: тип = значение [флаги]`.
- **Components** — дерево компонентов с отступами; `(нет)`, если их нет.
- **Event graph** — псевдокод в блоке ``` на языке вывода `uasset`:
  - `event Имя() [override] { ... }` — событие;
  - `if (условие) { ... } else { ... }` — ветвление (узел Branch);
  - `for (Элемент, Индекс in Коллекция) { ... }` — стандартные макросы циклов;
  - `let X = ВызовФункции(Аргумент: значение)` — чистые узлы как выражения;
  - `await ЗадержанныйВызов(...)` — latent-узлы (Delay и подобные);
  - `Объект.Метод(Имя: значение)` — вызов функции с именованными пинами.

Имена функций и пинов писать так, как они называются в движке (`PrintString`, `InString`), а не так, как
подписаны в редакторе.

## Правила

- Один трафарет — один asset или один конфигурационный файл. Путь в `Package` должен соответствовать зеркалу `project/Content` и настоящему пути в открытом UE-проекте.
- Трафарет описывает **намерение и связи**, а не раскладку узлов на экране. Позиции узлов не задаются.
- Если локальный Claude не может воспроизвести шаг (нет такого узла, другое имя пина) — он **не выдумывает
  замену**, а записывает расхождение в отчёт и спрашивает автора.
- **После сборки Claude** заносит фактические отличия в `project/BACKLOG.md` со ссылками на `.uasset`, PIE и docs; согласованные изменения в трафарет вносит владелец `ue-codex`. Нельзя переписывать текст под ошибку молча.
- Числа и значения в трафарете — заглушки, пока автор не утвердит их как баланс.
