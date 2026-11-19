# Источники

| Источник | Что это | Версия движка | Лицензия | Что изучено |
|---|---|---|---|---|
| [Lyra Starter Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine) | Образец Epic: модульный геймплей, GAS, Gameplay Tags, Common UI | 5.0–5.9 | Unreal Engine EULA | — |
| [Game Animation Sample](https://www.fab.com/listings/880e319a-a59e-4ed2-b268-b32dac7fa016) | Образец Epic: Motion Matching, Mover, Smart Objects | 5.4+ | Unreal Engine EULA | — |
| [Action Roguelike (Tom Looman)](https://tomlooman.com/unreal-engine-sample-game-action-roguelike/) | Компактный учебный проект на C++ | UE5 | см. репозиторий | — |
| [ALIS (World Reborn)](https://github.com/fallintodusk/alis) | Третий референс автора (не ALS). Открытая survival-игра на UE5 и C++: модульная архитектура, инвентарь, выживание, мир по реальной географии. Изучать архитектуру и готовые решения, не копировать | 5.8 | По компонентам (`LICENSE`): код внутри Unreal (C++, Blueprint, плагины) — MPL-2.0 (пофайловый copyleft: изменённые файлы ALIS открыть, остальной проект — нет); отдельные программы и сервисы — AGPL-3.0; помеченные интерфейсы — Apache-2.0. Пока изучаем решения, реализацию не копируем | — |
| [Lore](https://github.com/EpicGames/lore) | Система контроля версий Epic (MIT), 0.x | — | MIT | — |
| [rust-uasset](https://github.com/tera8m4/rust-uasset) | Читает `.uasset`/`.umap` (UE 4.21–5.8) без движка: Blueprint-графы как псевдокод, переменные, компоненты, зависимости, JSON | 4.21–5.8 | MIT-0 | Собран в облаке (коммит `54f14ac`), тесты зелёные; виджет-Blueprint из 5.8.2 читается. Логика геймплейного графа 5.8 не проверена — нужен наш Blueprint |
