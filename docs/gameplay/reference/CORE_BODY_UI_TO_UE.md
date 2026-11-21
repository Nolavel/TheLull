# Core survival → HUD → Debug
21.11.2026 • source reading + draft, не runtime.
 
## Источники и практический вывод
- [Hinterland — Condition and Character Status](https://hinterlandgames.zendesk.com/hc/en-us/articles/360042349471-Condition-and-Character-Status), официальный: четыре потребности, тренд направления/скорости, Condition отдельно и зависит от исчерпания потребностей. Не копировать оформление или закрытые формулы.
- [TLD community — Warmth](https://thelongdark.fandom.com/wiki/Warmth): знак и интенсивность изменения теплоты зависят от эффективной температуры; ветер, одежда, огонь и укрытие меняют её. Не переносить цифры в баланс.
- Hoarbound main @764d8276517dd9ddef52fcbe9b5f4e82b3190535: [Vitals HUD](https://github.com/Nolavel/Hoarbound/blob/764d8276517dd9ddef52fcbe9b5f4e82b3190535/docs/technical/VITALS_HUD.md), [HungerComponent](https://github.com/Nolavel/Hoarbound/blob/764d8276517dd9ddef52fcbe9b5f4e82b3190535/scripts/actors/player/henry/components/hunger_component.gd), [metabolism tests](https://github.com/Nolavel/Hoarbound/blob/764d8276517dd9ddef52fcbe9b5f4e82b3190535/tests/systems/test_metabolism_components.gd), [ThermalZone](https://github.com/Nolavel/Hoarbound/blob/764d8276517dd9ddef52fcbe9b5f4e82b3190535/scripts/systems/survival/thermal_zone.gd). Код: один clock, независимые потребности, normalized progress и сигналы, опыт трендов и температуры HUD. Тесты прочитаны, не запускались; не переносить Godot facade и шейдеры.
- Epic served UE 5.8: [Widget Blueprints](https://dev.epicgames.com/documentation/unreal-engine/widget-blueprints-in-umg-for-unreal-engine), [UProgressBar](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/UMG/UProgressBar?application_version=5.8), [Set Percent](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Progress/SetPercent), [Add to Viewport](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/UserInterface/Viewport/AddtoViewport), [Add Component by Class](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Game/AddComponentbyClass). [Event-driven UI](https://dev.epicgames.com/documentation/unreal-engine/driving-ui-updates-with-events-in-unreal-engine?lang=en-US) served 5.9, проверить паттерн в 5.8.4.
 
| State | Meaning | Owner |
|---|---|---|
| WorldTimeSeconds | game s | BP_SurvivalWorld |
| Warmth01, Rest01, Hydration01, Hunger01, Condition01 | normalized game state 0..1 | BPC_SurvivalBody |
| FeelsLikeC | effective test input, not core body temperature | level fixture → body API |
| LastDelta / LastStepHours | derived diagnostics | body |
| HUD/Debug | presentation only | widgets |
 
Тепло/холод — одна шкала, Cold01 производная 1−Warmth01. Condition не среднее четырёх шкал. Изменение по игровому времени, не FPS. Минимальный сценарий: холод уменьшает warmth, тепло восстанавливает; другие needs продолжают расходоваться; Condition реагирует на исчерпание. Test exposure −10/+5 — синтетические значения, не погода Key West и не физиологическая модель. Переход к реальной зоне/одежде/топливу заменяет input, а не создаёт вторую шкалу. Mock replenishment — только тест, не игровые ресурсы. Открытые вопросы: более широкий жанровый обзор, Miro, real climate/heat ownership, расход предметов, баланс. До них и до PIE статус draft.
