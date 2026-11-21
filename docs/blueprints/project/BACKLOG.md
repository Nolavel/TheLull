# TheLull — Blueprint build backlog (Claude Code / Unreal MCP)

**Статус: ожидает реального билда.** Первичная структура подготовлена Codex; **результатов проверки редактора пока нет**. После начала сборки Claude Local дополняет этот файл **только в своей ветке `ue-claudeflow`**, предварительно получив утверждённую копию stencil через `production` или явный handoff по правилам `AGENTS.md`. Нельзя редактировать ветку Codex или объявлять результат по списку MD-файлов.

Источники критериев: [манифест](../../gameplay/SURVIVAL_MANIFEST.md), [структура mirror](README.md), [Epic UE 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine), [Blueprint API 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI).

**Статус F00, 21.11.2026:** исправленный пакет из `ue-codex@1b15f38c4978167bb6e6f8a3fd190ba6cf31100b` опубликован в production как **revised draft / NEEDS RE-REVIEW**, не как готовое задание на сборку. Claude Cloud подтвердил исправление десяти замечаний, но полное повторное инженерное ревью каждого MD не завершено. Никаких UE-ассетов, Compile/PIE этим переносом не получено. Local может готовить окружение независимо; сборка конкретного трафарета — после его ревью и проверки MCP.

**Уточнение автора 21.11.2026 (заменяет прежний порядок):** сначала ядро survival по The Long Dark, затем минимальный UI и Debug UI с рабочими индикаторами; география только после этого. Штатная Third Person площадка нужна для запуска, не реконструкция квартала. Key West не отменён, но не является зависимостью core. Первичные F01/F02 используют контролируемый температурный вход, полная климатическая модель позднее.

## Не выполнено / ожидает локальной проверки

- **F−1-001 | NOT RUN:** подтвердить существующий Third Person Template, пакеты, camera/movement baseline в UE 5.8.4. Owner: Claude local.
- **F−1-002 | BLOCKED source identification:** PR #340, точные tower/gas IDs, bbox, две дополнительные shelter candidates; 727 не главный shelter. Owner: Claude + Codex handoff.
- **F−1-003 | NOT RUN:** собрать L_KeyWestBlockout, коллизии, маршруты и ≥2 укрытия; проверить в PIE. Owner: Claude local.

- **PRE-001 | OPEN — project setup:** автор 21.11.2026 подтвердил установленный UE 5.8.4; локальная инспекция не проводилась, проект ещё не создан. Claude Local создаёт Third Person Blueprint (None), проверяет `.uproject` и пакеты. Owner: Claude Local.
- **PRE-002 | OPEN — MCP setup:** Unreal MCP ещё не настроен (сообщение автора 21.11.2026). Claude Local настраивает подключение и проверяет capability inventory **Unreal MCP** (создание Structure, Interface, Blueprint Class, заполнение graph pins/links, создание level, Compile, Save, PIE, чтение actual graphs). Owner: Claude Code (local). Если нужная операция отсутствует, записать как блокировку, а не заменять её выдуманным endpoint.
- **F00-001 | NOT RUN:** Config + E_SimPhase + ST + BPI + BP + opt-in probe на L_SurvivalCore собраны по MD? Нужно Compile/Save и доказательство сохранения пакетов. Owner: Claude Code (local).
- **F00-002 | NOT RUN:** разбиение 3600 s vs 4×900 s, запрет двойной регистрации, отрицательного/нулевого/невалидного advance, fractional tail, duplicate clock, restore-before-init и после advance без симуляции, phase order/cache, reentry; фактические результаты PIE не получены. Owner: Claude Code (local).
- **F00-003 | NOT RUN:** текст ↔ actual asset graph → diff по переменным, типам, пинам, owner state и API; изменение каждого спорного места через отдельное согласование. Owner: Claude Code (local).

**Эти пункты не являются обнаруженными ошибками проекта.** Это открытые проверки, которые должны быть закрыты положительным или отрицательным доказательством.

- **PRE-003 | OPEN — pre-build stencil review:** Claude Cloud перепроверяет трафареты до локальной сборки, фиксирует SHA, технические замечания, точные исправления и статус REVIEWED / NEEDS REVISION / LOCAL VERIFICATION REQUIRED. Codex исправляет; Local получает обдуманный согласованный snapshot. Не заявлять PIE. Owner: Claude Cloud + Codex.

- **F00-004 | NEEDS RE-REVIEW:** Claude Cloud [review](https://github.com/Nolavel/TheLull/issues/3#issuecomment-7059415969) points 1–10 addressed in revised stencils: Float subtype, explicit initialization, enum/cache, private writer, duplicate clock, target loop, derived delta, rejection reasons, cleanup. Re-review required prior to local handoff. Local verification of actual precision, Map, graph nodes, pins and PIE remains OPEN. Existing textual checker only covers Event graph; function graphs and other asset types require separate inspection.

- **PRE-004 | OPEN — calibration:** после настройки проекта и MCP и pre-review выбранного MD выполнить минимальный цикл на E_SimPhase (Save/reopen/inspect); если доступны зависимости, проверить применение enum в Blueprint и PIE, иначе оставить PIE NOT RUN. 24.11.2026 — сначала setup, не обязательная сборка. Owner: Claude Local.
- **DESIGN-001 | OPEN — hypothesis from lab:** экономика мира может определять исход сильнее выбора игрока; план на завтра может не менять вечер. Не считать установленным фактом UE. Проверять на F01–F05 причинные связи, конечные ресурсы и разные решения в одной игровой ситуации. Owner: Codex.

- **CORE-001 | NEEDS REVIEW:** ST_CoreVitals + BPC_SurvivalBody, 4 потребности + Condition, один writer, clock-driven, fixture exposure.
- **CORE-002 | NEEDS REVIEW:** WBP_VitalsHUD, реальные snapshots и тренды.
- **CORE-003 | NEEDS REVIEW:** WBP_SurvivalDebug + L_SurvivalCore, состояние и тестовые команды, PIE pending.
- **CORE-004 | OPEN:** реальные ресурсы/действия/thermal zones. Mock replenishment не gameplay. Географию не начинать до рабочего ядра.
 
## Шаблон каждой новой записи (пополняет Claude Local после операции MCP)

```text
ID: F00-###
Area: /Game/.../Asset | Config/... | editor integration
Source stencil: docs/blueprints/project/...md @ <commit-sha>
Editor: UE 5.8.4 (confirmed: yes/no) | .uproject location (non-sensitive)
MCP: tool name/action + supported/unsupported; actual error if any
Epic UE 5.8: exact docs URL / pin or class confirmation
Expected (MD): ...
Actual (uasset/PIE/log): ...
Evidence: .uasset SHA/path, node report, compile output, PIE run/log (when available)
Manifest deviation: core loop / authoritative state / integration / repeated cost / testability
Severity: blocker | major | minor | improvement
Root cause: confirmed | hypothesis | unknown
Proposed change: ...
Reporter: Claude Local | Claude Cloud
Owner: Claude Local | Claude Cloud | Codex | author
Status: OPEN | BLOCKED | FIXED | VERIFIED | DEFERRED
Next review:...
```

## Честный цикл обратной связи

Claude Local фиксирует самопроверку на реальном UE; Claude Cloud отдельно добавляет замечания к переданному SHA/артефактам, не подменяя PIE и не закрывая локальные проверки по одному тексту. До сборки blockers окружения не запрещают работу Codex над согласованными трафаретами.

- После **каждого** реально собранного ассета Claude Local проверяет его, не откладывая на конец всех систем; пишет подтверждённый mismatch или улучшение с evidence.
- Под `FIXED` понимается изменение реального asset или MD в ветке владельца; `VERIFIED` требует повторного Compile/Save/PIE где уместно.
- Изменение публичного контракта типа/pin/path не выполняется молча: Claude передаёт Codex precise feedback, Codex правит stencil в `ue-codex`, только автор решает слияние в `production`. Отрицательные результаты сохраняются.
- Backlog проверяется **против четырёх требований манифеста**: игрок/loop, источники TLD+жанр+Hoarbound+Key West, UE API/владельцы, причинные PIE/живые тесты. Факт успешного Compile — не proof of gameplay.
