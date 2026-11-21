# TheLull — F00: с чего строится survival и что именно передавать в UE

**21.11.2026. Статус: исследовательская исходная карта, не утверждение новых механик, не баланс, не работающий Blueprint.**  
Ветка: `ue-codex`; `production` не изменять. Прежде чем придумывать очередную D-серию, исследовать источник → проверить существующий опыт Hoarbound → вывести TheLull/Key West-специфику → сформулировать исполнимый контракт UE → проверить один реальный игровой выбор.

**Рабочий статус 21.11.2026:** этот документ — исследование, а не набор готовых ассетов. Его обязательная нормативная рамка — [манифест](../SURVIVAL_MANIFEST.md). **Первый реальный путь в редактор:** `ST_SimStep` → `BPI_SimStepReceiver` → `BP_SurvivalWorld` → `BP_F00ClockProbe` по [трафаретам зеркального UE-проекта](../../blueprints/project/README.md); Claude Code создаёт и проверяет реальные assets через Unreal MCP, затем пишет backlog, статус пока только MD. В F00 сначала проверяется честный clock; room/body/heat и полная приёмка 727 относятся к F01–F05, не выдаются за собранное.

## 0. Не начинаем с агента и не начинаем с одежды

**Survival = персонаж с конечными физическими возможностями, живущий во времени в изменяющейся среде; любое действие обменивает время, ресурсы и состояние тела на новую возможность.** Источник конкретного референса: [официальный The Long Dark — Survival Mode](https://www.thelongdark.com/survival-mode/). Там *Hunger, Thirst, Fatigue, Cold* и *Condition*, а время — основная цена действий. Это **грамматика**, не инструкция копировать скорость метаболизма, интерфейс или permadeath.

Минимальная причинная схема, **не список метрик ради полноты**:

```text
WORLD & TIME (погода, освещённость, доступность укрытий, конечный лут)
       |               |
       v               v
ENVIRONMENT <--> SHELTER / HEAT / WATER / FOOD
       |               |
       +----> BODY <----+---- EQUIPMENT / CARRIED LOAD
                    |
 PLAYER ACTION (уйти, вернуться, отдыхать, искать, чинить, готовить)
       | 
       +-- оплачивает единое игровое время и ресурсы
       +-- меняет наблюдаемый мир, тело, предметы
       +-- оставляет следующий выбор ИГРОКУ
```

Фундамент — **один clock + неизменность владения состоянием + причинное обновление систем + реальные цены действий**, а не искусственный интеллект, оптимизирующий написанную нами же policy.

## 1. Что уже известно, а не нужно «переоткрывать» в Python

| Источник | Подтверждённый факт / уже существующая реализация | Что забираем | Что НЕ переносим как истину |
|---|---|---|---|
| [TLD Survival Mode](https://www.thelongdark.com/survival-mode/) | Четыре потребности, Condition, время/калории как цена действия, изменяющиеся погода и время суток; без готовых ответов игроку | Сцепление потребностей, мира и решений | Коэффициенты и поведение конкретного игрока |
| [Hoarbound: Systemic Survival Foundation](https://github.com/Nolavel/Hoarbound/blob/main/docs/technical/SURVIVAL_SIMULATION_ROADMAP.md) | Уже описана migration-последовательность от общего времени к actions/body/shelter, не big-bang rewrite | Архитектурный принцип «данные → детерминированная симуляция → presentation» | Слепое копирование GDScript |
| [Hoarbound: SimulationClock](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/time/simulation_clock.gd) | В `main` есть мировой clock, `advance_hours`, субшаги, упорядоченные participants, блокировка realtime во время длительной операции | Один authoritative time owner; realtime и sleep/work через один путь | Считать blueprint-порт готовым |
| [Hoarbound: TimeCostedActionSystem](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/actions/time_costed_action_system.gd) | Действие имеет жизненный цикл, прерывание и честный расход времени. Gameplay owner решает, что именно потратить/выдать | Отделить «оплатить время» от «проверить ресурс / создать результат» | Платить два раза за одно действие |
| [Hoarbound: ThermalZone](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/survival/thermal_zone.gd) + [ThermalManager](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/survival/thermal_manager.gd) | В `main` уже существуют зоны холода, ветер/экспозиция, нагрев, утечка через открытые проёмы, одежда и wetness | Термические связи и собственники, а не баланс Godot | Считать это проверенной физиологией или UE-подтверждением |
| [Hoarbound: Experience Pillars](https://github.com/Nolavel/Hoarbound/blob/main/docs/game_design/EXPERIENCE_PILLARS.md) + Miro `DESIGN 07 — Обещание игроку` | Цель игрового опыта: маленькое намерение, срыв обстоятельствами, импровизация, облегчение от укрытия, желание прожить следующий день | Критерий, ради чего связываем системы | Выдавать рабочую цель за доказанную привлекательность |
| [Hoarbound: Key West Design Doctrine](https://github.com/Nolavel/Hoarbound/blob/main/docs/world/KEY_WEST_DESIGN_DOCTRINE.md) | Реальный город сначала; дома и улицы создают shelter/ветер/маршруты, даже если интерьер не играбелен | Местоположение как gameplay, не снежный декор | Переносить особенности канадского леса в Key West |
| [Epic: Gameplay Framework 5.8](https://dev.epicgames.com/documentation/unreal-engine/game-objects-in-unreal-engine?lang=en-US) | Actors, ActorComponents, Data Assets — штатные элементы для Blueprint-композиции | Реалистичный первый Blueprint-only путь | Заранее навязывать GAS, ECS, Verse или C++ |

**Статусы:** `TLD observed` (описан производителем), `Hoarbound implemented` (файл реально есть в `main`, но не утверждаем завершённый игровой опыт), `Key West source` (документальный факт), `TheLull hypothesis`, `UE prototype pending`. D1.3–D2.0 — **контроль работы собственных Python-правил**, не доказательство того, чего хотят игроки.

## 2. Порядок строительства всей survival-грамматики

`F00 / Time + state` → `F01 / Climate and shelter` → `F02 / Body (cold, fatigue, hunger, thirst, condition)` → `F03 / Resources and equipment` → `F04 / Actions with time, interruption and consequences` → `F05 / Day-exit-return-night` → `F06 / Player discovery and feedback`.

Первые пять — **зависимости реализации**; их не нужно растягивать на 5 отдельных новых симуляционных лабораторий. Изучаем известные образцы, потом собираем UE-проверку. Каждая новая переменная должна иметь **собственника, источник изменения, потребителя, save-contract и проверяемую альтернативу**.

## 3. Первый практически собираемый Blueprint-контракт F00

**Это схема к сборке, ещё не созданные `.uasset`, не утверждённый production API.** Начинаем без GAS: для одного игрока не нужна тяжёлая ability-архитектура до появления реальной необходимости. Сперва Blueprint Actor + Actor Components + Structs + SaveGame, потом при необходимости C++.

| Предлагаемый Blueprint / Struct | Состояние или API (тип) | Владелец записи; кто читает |
|---|---|---|
| `BP_SurvivalWorld` (Actor) | `WorldTimeSeconds: Double`; `AdvanceGameTime(DeltaGameSeconds: Double, Reason: GameplayTag)`; `GetWorldTime` | **Единственный писатель clock**. Все действия вызывают API; UI/свет читают |
| `ST_SimStep` (Blueprint Struct) | `StartSeconds: Double`, `EndSeconds: Double`, `DeltaSeconds: Double`, `Reason: GameplayTag` | Создаёт мировой clock; systems consume |
| `BPC_Climate` (ActorComponent на world actor) | `AirTemperatureC: Float`, `WindSpeedMps: Float`, `WindDirection: Vector`, `WeatherState: GameplayTag` | Climate writes; room/route/body read. Погода **не знает** намерение игрока |
| `BPC_RoomThermal` (ActorComponent на actor комнаты 727) | `ZoneId: Name`, `TemperatureC: Float`, `WindExposure01: Float`, `SealedFraction01: Float`, `HeatInput` (поток, пока без предрешённых единиц), `StoredHeat` (внутренняя модель) | Room writes; body и визуализация read. **Тёплая комната**, а не булевое `bIsIndoorSafe` |
| `BPC_SurvivalBody` (ActorComponent на Henry) | `CoreTemperatureC: Float`, `Calories: Float`, `Hydration: Float`, `Fatigue01: Float`, `Condition01: Float` | Body writes. Подсистемы условий воздействуют через единый update; HUD read-only. Конкретная шкала и пороги — **не баланс из Python** |
| `ST_ActionRequest` (Blueprint Struct) | `ActionId: GameplayTag`, `Target: Actor Reference`, `DurationGameSeconds: Double`, `bInterruptible: Boolean` | Вызывает player/action; не содержит «добычу дров» как жёсткое свойство |
| `BPC_TimeActionRunner` (ActorComponent) | `CanStartAction`, `StartAction`, `StopAction`, `OnActionCompleted/Cancelled` | **Единственный инициатор оплаты длительных действий через World**. Gameplay target owner выдаёт/списывает ресурс строго один раз |
| `SG_TheLull` (SaveGame Blueprint) | `WorldTimeSeconds` + `BodyState` + `RoomStates` + `ItemInstances` | Снимает snapshots авторитетных владельцев; никогда не «восстанавливает» симуляцию повторным расходом времени |

`BPC_Climate` и `BPC_SurvivalBody` — **заготовки интерфейсов полного фундамента**, но не требование сразу реализовать пять survival meters. Для первого теста достаточно clock, одной температуры тела/теплоизоляции, одной комнаты, одного источника тепла и конечного топлива. Остальные поля зарегистрированы как кандидаты, **не отправлены в production**.

### Последовательность одного рабочего Blueprint-события

```text
PLAYER presses Interact on 727 window
  → Window.CanSeal() verifies valid board and window state
  → BPC_TimeActionRunner.StartAction(SealWindow)
  → BP_SurvivalWorld.AdvanceGameTime(requested slice, Reason=Action)
      → Climate samples for THIS interval
      → Fuel/HeatSource consumes its fuel for THIS interval
      → RoomThermal evolves heating/leaks
      → Body evolves from actual room/wind + gear
      → Needs integrate against SAME time
  → OnActionCompleted:
      Window marks seal; inventory consumes reserved board ONCE
      → Room changes SealedFraction01
      → SaveGame preserves both resource and change
  → OnActionCancelled: account only elapsed time and explicitly agreed refunds
```

**Реализация в Blueprint графе:** World clock должен последовательно вызывать **явные** `SimulateStep(ST_SimStep)` на зарегистрированных потребителях; **не** полагаться на порядок Event Tick разных Actor. Для длительного действия блокировать параллельное обычное начисление времени. Удобный стартовый размер шага — до 15 игровых минут из Hoarbound roadmap; это **технический временный quantum**, не баланс. Никакой `Set Global Time Dilation` для восьми часов сна.

### Первый acceptance-сценарий в UE (не агент, не будущие исследования)

Точка: **одна холодная комната 727 Fort Street, одна доступная щель/окно, одна печь, конечные дрова, одна доска**.

Игрок сам решает:
- потратить время и доску на снижение утечки;
- потратить дрова, пытаясь компенсировать утечку теплом;
- ничего не делать и принять последствия для тела.

**Никаких заранее выигрышных чисел:** параметры provisional, затем исследовать/сравнить. Нужны наблюдаемые температура комнаты, количество дров, состояние окна, время и состояние тела — без дополнительной шкалы «интереса».

**Проходные критерии:**
1. `AdvanceGameTime(8h)` и последовательные субшаги той же длины дают совместимые результаты; потребности обновлены **один раз**, даже во сне/работе.
2. Закрытая щель меняет термическое поведение комнаты, **а не** переключает волшебный безопасный флаг.
3. Дрова конечны; нельзя сжечь одно полено дважды; прерванная работа не создаёт готовый результат.
4. Через Save/Load состояние окна/печи/комнаты/тела/времени продолжает развитие без reset и повторного списания.
5. В одном и том же старте у трёх стратегий обнаруживается **разная физическая цена**, но ни одна не объявляется интересной без наблюдения за человеком.

## 4. Отдельная параллельная исследовательская дорожка: Key West, а не «лес с пальмами»

**Документальные основания:** [Florida Keys tourism — конч-дома, веранды, shutters, крышные вентиляционные отверстия](https://visitfloridakeys.com/plan-your-trip/plan-book/insiders-guide/key-west-architecture-treasures-tour); [городские HARC architectural guidelines](https://www.cityofkeywest-fl.gov/DocumentCenter/View/1551/HARC-Guidelines-PDF). Актуальный канон адаптации — Hoarbound [Key West Design Doctrine](https://github.com/Nolavel/Hoarbound/blob/main/docs/world/KEY_WEST_DESIGN_DOCTRINE.md) и Miro `DESIGN 03 — Причём тут доски?`. **Реальный климат Key West не равен вымышленной катастрофической зиме**.

| Доказанный факт места | Исследуемая игровая гипотеза | Кандидат для UE | Проверка в TheLull |
|---|---|---|---|
| Исторические дома имели большие окна, shutters, веранды, вентиляционные элементы | В морозных условиях защита от сквозняка и выбор **одной пригодной комнаты** важнее «вошёл внутрь = тепло» | `FRoomThermalState.SealedFraction01`, `AirLeakageFactor`; `BPC_RoomThermal` | 727 до/после одного ремонта; отдельное сравнение от расхода топлива |
| Улицы, здания и заборы реального города формируют пространственные коридоры | Ветер и экспозиция маршрута создают отличия даже между двумя близкими дорогами | `FRouteSegment.Exposure01`, `WindOcclusion01` | Сравнить путь вдоль защищённых домов и открытый участок; игрок сам читает признаки |
| На острове морская вода окружает город; существование питьевого ресурса не следует из воды на карте | Поиск **питьевой** воды и источник тепла могут конкурировать с обогревом и сушкой | `Item.WaterPotability`, `WaterVolumeL`, `ProcessHeatDemand` **гипотеза** | Сначала подтвердить инфраструктуру/доступность пресной воды и реальные процессы, затем экспериментировать |
| Много деревянных и отличающихся по типологии построек | «Разобрать дом на топливо» может влиять на его пригодность как убежища, не только на inventory | `ResourceSourceId`, `RemainingMaterial`, `ShelterIntegrity` **гипотеза** | Одна доска: закрыть проём или израсходовать на другую цель; без дублирования ресурсов |

**Не переносить в код без дополнительного исследования:** абсолютные показатели теплопередачи конкретного дома, поведение морской воды при вымышленной экстремальной зиме, географически «автоматическую» доступность пресной воды, свойства всех деревянных строений, snow/ice как идентичный северной Канаде. Конкретный 727 и First Exit A — реальные production-референсы, но изменять их сцены без отдельного решения автора нельзя.

## 5. Шаблон следующей карточки: одна связь → одна Blueprint-проверка

**ID / рабочее название:** `F01 | 727 window sealing → room heat retention`  
**Зачем игроку:** что именно становится возможно после действия, и с чем оно конкурирует?  
**База в жанре (источник):** факт + версия/ссылка, не «в TLD вроде было».  
**Hoarbound:** код или наблюдение; `implemented` / `verified in build` / `planned`.  
**Key West:** физический/исторический факт, гипотеза для экстремального холода, локальная форма.  
**Реальный владелец UE:** класс / компонент, writer, readers.  
**Переменные UE:** имя, тип, диапазон/единицы, Serialize?  
**Граф события:** сигнал → предусловия → цена → изменение → возможное прерывание → feedback.  
**Приёмка Blueprint:** конкретные входы и ожидаемые *относительные эффекты*, без переносимых lab-коэффициентов.  
**Результат:** `source verified` / `Hoarbound implemented` / `Python lab contract` / `UE tested` / `human observed` / `rejected`.  
**Отрицательный результат:** что не сработало или не создало отличимого выбора.  
**Решение владельца:** `candidate` / `accepted` / `deferred` / `rejected`.

**Порядок дальнейшей работы:** провести конкретное сопоставление TLD ↔ Hoarbound ↔ физика Key West ↔ TheLull; оформлять компактные **coupling-карточки** только по полезным расхождениям. Не добавлять новых исследовательских D-агентов без задачи, которую нельзя решить существующими данными или Blueprint-пилотом.

### Источники, не смешивать их статусы
- [The Long Dark, official Survival Mode](https://www.thelongdark.com/survival-mode/)
- [Hoarbound, Experience Pillars](https://github.com/Nolavel/Hoarbound/blob/main/docs/game_design/EXPERIENCE_PILLARS.md)
- [Hoarbound, Key West Doctrine](https://github.com/Nolavel/Hoarbound/blob/main/docs/world/KEY_WEST_DESIGN_DOCTRINE.md)
- [Hoarbound, Simulation Clock code](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/time/simulation_clock.gd)
- [Hoarbound, Action Time code](https://github.com/Nolavel/Hoarbound/blob/main/scripts/systems/actions/time_costed_action_system.gd)
- [Epic, UE 5.8 Actor / Component / DataAsset](https://dev.epicgames.com/documentation/unreal-engine/game-objects-in-unreal-engine?lang=en-US)
- [Epic, UE 5.8 SaveGame API](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/USaveGame?application_version=5.8)
- [TLD→TheLull research protocol](TRANSLATION_TO_THELULL.md)
- [TheLull research mandate](RESEARCH_MANDATE.md)
