# L_KeyWestBlockout — первый игровой level

**Цель:** `<ProjectRoot>/Content/Maps/L_KeyWestBlockout.umap`, package `/Game/Maps/L_KeyWestBlockout`. Один MD — один level asset. Статус planned, UE не запускался. [Манифест](../../../../gameplay/SURVIVAL_MANIFEST.md). Это игровая площадка survival, не отдельная абстрактная лаборатория.

## Источники и границы

Hoarbound [PR #340](https://github.com/Nolavel/Hoarbound/pull/340), merge `edbcf0218838416a6ca129639a3a99f64527daae`: исправлены Lofts, Douglass Center, городские контуры и 727 по permit. В Hoarbound локально проверены 156 suites и 69 reality tests; это не тесты TheLull. [Географическая спецификация](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/docs/superpowers/specs/2026-11-18-key-west-727-reconstruction-design.md) — аудит 400×400 м вокруг 727; исходные chunks `-8:3`, `-7:3`. Использовать [frame](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/data/world/key_west/reality/config/frame.json), [documented buildings](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/data/world/key_west/reality/config/documented_buildings.json), [city footprints](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/data/world/key_west/reality/config/city_footprints.json), [export manifest](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/data/world/key_west/reality/editor_export/manifest.json). Проверить актуальность export digest относительно PR; старый архив не считать новым фактом. Выдерживать реальную географию, отдельно игровые назначения.

[727 data](https://github.com/Nolavel/Hoarbound/blob/edbcf0218838416a6ca129639a3a99f64527daae/data/world/key_west/reality/landmarks/kw_727_fort_st.json): origin Godot `[-3530.487, 1.23, 1583.02]`; X east, Z south, Y up (metres, EPSG:32617 и NAVD88). Это координатный anchor, не shelter/spawn. Предлагаемый локальный UE frame X east, Y south, Z up, см: `(100*(x-x0),100*(z-z0),100*(y-y0))`; проверить ориентацию, геометрию и масштаб до массового импорта. Не подтверждать совпадение без проверки в UE.

## Состав квартала

| Объект | Роль |
|---|---|
| 727 Fort St | Реальный контур permit 20-6136, один ориентир/возможный shelter. Главный shelter отменён. |
| Lofts at Bahama Village, 918 Fort St | Legistar 22-3575: пять документированных масс; выбранное помещение может стать кандидатом shelter, остальные закрытые. Plans as designed, not surveyed. |
| Frederick Douglass Community Center, 111 Olivia St, gym | Legistar 21-7769: документированный ориентир/кандидат; не обещать доступность всего здания. |
| Вышка и АЗС | Проверить точные IDs и координаты в utilities/POI/геоданных. Не путать с другой вышкой First Exit и не придумывать положение; роль shelter не назначена. |
| Ещё два здания | Выбрать по проверенным footprints, доступным входам и маршрутам; записать IDs и обоснование. Кандидаты shelter, не назначать главное. |
| Остальные здания | Простая наружная масса, закрытая коллизия, без интерьера и лута. |

Не утверждать, что все объекты внутри 400×400 м до проверки. Использовать минимальный связный охват реальных объектов; если ориентиры за пределами, уточнить границы без перемещения зданий. Не строить весь остров.

## Сборка Claude Code + Unreal MCP

1. Проверить локальный `.uproject`, installed UE 5.8.4, MCP capabilities. Основа: [Epic Third Person Template](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine?application_version=5.8), Blueprint, Variant None. Использовать действующие Character/GameMode/input/camera/animation; проверить их package paths. Если проект уже существует, не создавать поверх него новый.
2. Создать этот level с GameMode шаблона, PlayerStart на проходимой улице, базовым светом/геометрией. PIE: ходьба, мышь, штатная камера. Не создавать другой контроллер.
3. Собрать улицы и footprint-массы по источникам, реальные входы/стены/пол выбранных помещений. Collision; без декоративных ассетов и глобальных процедурных систем. Не переносить Hoarbound как Godot-проект. Каждый новый самостоятельный asset — отдельный MD по реальному пути; обычные размещённые в этой карте примитивы описываются в данном level stencil.
4. Установить подтверждённые tower/gas IDs, bbox, дополнительные shelter candidates. Если источник недоступен — BLOCKED source в backlog, не фиктивная география.
5. Compile/Save/PIE: проходимость улиц, коллизии закрытых зданий, вход/выход ≥2 укрытий, минимум два направления, камера и масштаб. Зафиксировать top-down и street-level кадры, размеры и время прохода. Ни одна точка не является обязательной целью.
6. Только после F−1 добавить `BP_SurvivalWorld` и тестовый `BP_F00ClockProbe` в этот level; `bRunProbe=false` в обычном PIE, true лишь для отдельного теста. Не заменять карту пустой TimeLab. **F00 startup (Level Blueprint этого же .umap):** BeginPlay → Get All Actors Of Class BP_F00ClockProbe → если ровно один instance с bRunProbe=true, пропустить default init (probe сам вызовет InitializeNewGame/RestoreWorldTime); если больше одного активного — Print String error и не запускать clock; если нет активного probe, Get All Actors Of Class BP_SurvivalWorld → ровно один → InitializeNewGame → проверить true, иначе error. Для чтения флага probe использовать Instance Editable, не Private. В F−1, до появления clock/probe, этого графа нет. Никакого сброса времени в Actor BeginPlay, Delay только в тестовом probe. [Backlog](../../BACKLOG.md).

**Приёмка F−1**: играется штатным персонажем Third Person, география документирована, альтернативные маршруты/укрытия доступны, остальные здания закрыты, 727 не назначен главным. Никакого утверждения о готовности survival или fun. Runtime-результаты ещё не получены.
