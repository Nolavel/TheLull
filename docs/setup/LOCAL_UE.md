# Первый запуск UE 5.8 и проект TheLull — инструкция для локального Claude Code

Статус: черновик в `ue-claudeflow`, в `production` не вливать, пока не проверена конфигурация Zen.

## Железо

HP 15s-du0xxx: **4 ГБ DDR4**, Intel HD 620 (видеопамять из тех же 4 ГБ), на `C:` ~20 ГБ свободно,
внешний HDD USB 3.0 — `H:` (~400 ГБ свободно). Epic: минимум 8 ГБ RAM
([Hardware and Software Specifications](https://dev.epicgames.com/documentation/unreal-engine/hardware-and-software-specifications-for-unreal-engine)).

Решение автора: железо не покупаем, сначала измерения. Конфигурацию записать для истории: Product Number
(наклейка или `msinfo32`), слоты и модули памяти — по HWiNFO или CPU-Z (вкладка SPD); Диспетчеру задач
в части слотов не верить.

## Где что хранится

| Место | Что | Как |
|---|---|---|
| `H:\TheLull` | Рабочий проект целиком; это клон репозитория | Unreal работает прямо отсюда |
| GitHub, ветка `ue-claudeflow` | Код, конфиги, документы, Blueprints, карты и небольшие ассеты | commit/push локальным Claude, ревью облачным |
| Google Drive `TheLull/Backups/` | Датированные полные архивы проекта | `tools/backup.ps1` после работы, без автосинхронизации рабочей папки |

Не хранить нигде: сам движок, `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`.

Перед загрузкой ассета на GitHub — проверить лицензию (репозиторий публичный) и размер:
файлы больше 50 МБ не коммитить (GitHub отклоняет файлы больше 100 МБ); для таких позже Git LFS.

## Цель вечера

1. Установить UE 5.8.4 на `H:` и вынести DDC с `C:` (разделы 1–2).
2. Создать проект TheLull в клоне репозитория, открыть пустой редактор на 4 ГБ, подключить MCP (разделы 3–5).
   Задача — реальные данные: работает ли редактор и можно ли изучать интерфейс.

Никаких игровых систем и новых зависимостей.

**Долгое «не отвечает» — не повод завершать UE:** первая компиляция шейдеров на HDD идёт долго.
Смотреть в Диспетчере задач: CPU или диск заняты — ждать; CPU и диск около нуля несколько минут при памяти
на пределе — вероятно, зависание, решение о завершении за автором. Записать, на каком шаге.

## 1. Установка

1. Launcher → UE **5.8.4** в `H:\Epic\UE_5.8`. В «Options» снять всё, кроме Windows: другие платформы,
   «Editor symbols for debugging».
2. Launcher → Settings → «Edit Vault Cache Location» → `H:\Epic\VaultCache`.
3. Закрепить букву `H:` (Управление дисками → «Изменить букву диска»), чтобы пути не менялись.

## 2. DDC (Zen) — до первого запуска редактора

Порядок выбора пути Zen
([Epic: DDC](https://dev.epicgames.com/documentation/unreal-engine/using-derived-data-cache-in-unreal-engine),
[Epic: Zen как cooked output store](https://dev.epicgames.com/documentation/unreal-engine/zenserver-as-cooked-output-store-in-unreal-engine)):

1. `UE-ZenDataPath` или `-ZenDataPath=` — главнее всего;
2. иначе Local DDC Path (Editor Preferences, `UE-LocalDataCachePath`, `-LocalDataCachePath=`) — Zen пишет
   в подпапку `Zen`;
3. иначе — `C:` (`C:\ProgramData\Epic\Zen\Data\` или `%LOCALAPPDATA%\UnrealEngine\Common\Zen\Data`).

Шаги:

1. Показать автору, что уже задано:
   ```powershell
   [Environment]::GetEnvironmentVariable("UE-ZenDataPath","User")
   [Environment]::GetEnvironmentVariable("UE-ZenDataPath","Machine")
   [Environment]::GetEnvironmentVariable("UE-LocalDataCachePath","User")
   Test-Path C:\ProgramData\Epic\Zen\Data; Test-Path "$env:LOCALAPPDATA\UnrealEngine\Common\Zen\Data"
   ```
2. С согласия автора:
   ```powershell
   New-Item -ItemType Directory -Force H:\UE\DDC | Out-Null
   setx UE-LocalDataCachePath "H:\UE\DDC"
   ```
   Если `UE-ZenDataPath` уже задан — он перекроет этот путь; не трогать, сообщить автору.
3. Перезапустить Launcher и терминал. Записать свободное место на `C:`.

**Ничего не удалять.** Старые каталоги Zen на `C:` — только сообщить размер; очистку решает автор
после остановки `zenserver.exe`.

## 3. Проект TheLull

1. Клон: `git clone https://github.com/Nolavel/TheLull H:\TheLull`, затем `git -C H:\TheLull checkout ue-claudeflow`.
2. Unreal → New Project → Games → **Blank**, **Blueprint**, **без Starter Content**, Location `H:\`,
   Name `TheLull`. Проект ляжет в клон рядом с `docs/` и `AGENTS.md`.
   Если редактор откажется создавать проект в непустой папке — создать во временной `H:\TheLull_tmp`
   и перенести содержимое в `H:\TheLull`, сообщив автору.
3. Сразу, до работы (Project Settings), для HD 620:
   - Rendering → Dynamic Global Illumination: **None**; Reflection Method: **Screen Space**;
   - Shadow Map Method: **Shadow Maps** (без Virtual Shadow Maps);
   - Engine Scalability: **Low**; Editor Preferences → «Use Less CPU when in Background» вкл.
4. Если редактор падает с ошибкой D3D12 — запуск с `-dx11`, записать текст ошибки.

## 4. Проверки (результат — автору цифрами)

- Строка `LogZen` / `LogDerivedDataCache` из `H:\TheLull\Saved\Logs\TheLull.log`: путь Zen на `H:`.
- Свободное место на `C:` до и после первого открытия.
- Время первого открытия, FPS пустого уровня (`stat fps`), память — из Диспетчера задач.

## 5. Unreal MCP

Источник: [Unreal MCP in Unreal Editor (5.8)](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?application_version=5.8).
Плагин экспериментальный.

1. Edit → Plugins: включить **Unreal MCP** и **All Toolsets**, перезапустить редактор.
2. Консоль редактора: `ModelContextProtocol.GenerateClientConfig ClaudeCode`.
3. Запустить Claude Code из `H:\TheLull`. Сервер: `http://127.0.0.1:8000/mcp`.
4. Проверка: Claude создаёт куб на уровне и читает список акторов.

Безопасность: сервер без аутентификации, только localhost; порт 8000 наружу не открывать.
Сгенерированный конфиг MCP — проверить перед коммитом, личных путей и токенов в git не класть.

## 6. Коммит и резервная копия

1. `git status` — убедиться, что не попали `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`
   и файлы больше 50 МБ.
2. Commit и push в `ue-claudeflow`: проект, конфиги и запись в `CHANGELOG.md` с цифрами из раздела 4.
3. Резервная копия: `powershell -File H:\TheLull\tools\backup.ps1` — архив `TheLull_ГГГГ-ММ-ДД_ЧЧММ.zip`
   в `H:\Backups`; затем загрузить его в Google Drive `TheLull/Backups/` (вручную или через папку Drive
   для компьютера — но не рабочую папку проекта).

Облачный Claude забирает изменения через `git fetch`, правит и пушит в ту же ветку.
Перед работой — всегда `git pull`.

## 7. Тест чтения Blueprint (после раздела 6)

Цель: проверить, что облачный Claude восстанавливает логику из `.uasset` без редактора. Источник истины —
`.uasset` в Unreal; текст и JSON из rust-uasset — только представление для анализа.

1. `Content/Tests/BP_LogicTest` (Actor), переменная `bIsCold` (Boolean).
2. `BeginPlay → Branch(bIsCold) → True: Print String "Cold" / False: Print String "Warm"`.
3. Сохранить, commit и push в `ue-claudeflow`. Сделать скриншот графа и передать автору (не коммитить);
   облачному Claude граф не показывать до его разбора.
4. Облачный Claude: `uasset Content/Tests/BP_LogicTest.uasset` и `--nodes`.

Успех — восстановлены событие, условие по `bIsCold`, порядок выполнения и оба исхода с их строками.
Следующий тест — функции, собственные события и обращение к другому объекту.
