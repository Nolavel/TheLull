# Первый запуск UE 5.8 на ноутбуке автора — инструкция для локального Claude Code

Статус: черновик в `ue-claudeflow`, в `production` не вливать, пока не проверена конфигурация Zen.

## Железо: главное ограничение — память

HP 15s-du0xxx: **4 ГБ DDR4**, Intel HD 620 (видеопамять берёт из тех же 4 ГБ), системный диск ~20 ГБ
свободно, внешний HDD USB 3.0 500 ГБ (~400 ГБ свободно). Epic: минимум 8 ГБ RAM, рекомендовано 32 ГБ
([Hardware and Software Specifications](https://dev.epicgames.com/documentation/unreal-engine/hardware-and-software-specifications-for-unreal-engine)).
С 4 ГБ редактор почти наверняка уйдёт в подкачку и будет зависать; перенос файла подкачки и настройки кэша
это не лечат.

Решение автора: **железо сейчас не покупаем**. Работаем на том, что есть; сначала измерения.

Конфигурацию записать для истории (не для покупки): точный Product Number (наклейка снизу или
`Win+R` → `msinfo32`), слоты и модули памяти — по **HWiNFO** или **CPU-Z** (вкладка SPD).
Диспетчеру задач в части слотов не верить: он берёт данные из BIOS.

## Цель вечера

1. Установка UE 5.8.4 на внешний диск и настройка DDC (разделы 1–2).
2. Эксперимент: пустой редактор на 4 ГБ, `UE_Lab` и MCP (разделы 3–5). Задача — реальные данные:
   откроется ли редактор и можно ли хотя бы изучать интерфейс. Не разработка.

Перед запуском закрыть браузер и всё лишнее. **Долгое «не отвечает» — не повод завершать UE:** первая
компиляция шейдеров на HDD идёт долго. Смотреть в Диспетчере задач на CPU, диск и память:
- CPU или диск заняты — процесс работает, ждать;
- CPU и диск около нуля дольше нескольких минут, память на пределе — вероятно, зависание; решение
  о завершении принимает автор. Записать, на каком шаге это случилось.

Никаких игровых систем, архитектурных каркасов и новых зависимостей. Тестовый проект `UE_Lab` — не начало
TheLull: он живёт **вне** репозитория и в `production` не попадает.

## Исходные условия

- Windows; движок и `UE_Lab` — на внешнем HDD USB 3.0 (400 ГБ).
- Буква внешнего диска неизвестна. Ниже — `<X>:`. Узнать у автора, посмотрев в Проводнике; предложить
  закрепить её (Управление дисками → «Изменить букву диска»), чтобы пути не менялись при переподключении.

## 1. Установка

1. Launcher → установить UE **5.8.4** в `<X>:\Epic\UE_5.8`.
   В «Options» снять: целевые платформы кроме Windows, «Editor symbols for debugging».
2. Launcher → Settings → «Edit Vault Cache Location» → `<X>:\Epic\VaultCache`.

## 2. DDC (Zen) — до первого запуска редактора

С UE 5.4 локальный DDC хранит Zen. Порядок выбора пути
([Epic: DDC](https://dev.epicgames.com/documentation/unreal-engine/using-derived-data-cache-in-unreal-engine),
[Epic: Zen как cooked output store](https://dev.epicgames.com/documentation/unreal-engine/zenserver-as-cooked-output-store-in-unreal-engine)):

1. `UE-ZenDataPath` (переменная) или `-ZenDataPath=` — **главнее всего**;
2. иначе Local DDC Path из Editor Preferences, `UE-LocalDataCachePath` или `-LocalDataCachePath=` —
   тогда Zen пишет в подпапку `Zen` этого пути;
3. иначе — системный диск (`C:\ProgramData\Epic\Zen\Data\` или `%LOCALAPPDATA%\UnrealEngine\Common\Zen\Data`).

Шаги:

1. Проверить, что ничего не задано раньше, и показать результат автору:
   ```powershell
   [Environment]::GetEnvironmentVariable("UE-ZenDataPath","User")
   [Environment]::GetEnvironmentVariable("UE-ZenDataPath","Machine")
   [Environment]::GetEnvironmentVariable("UE-LocalDataCachePath","User")
   Test-Path C:\ProgramData\Epic\Zen\Data; Test-Path "$env:LOCALAPPDATA\UnrealEngine\Common\Zen\Data"
   ```
2. Задать путь (с согласия автора):
   ```powershell
   New-Item -ItemType Directory -Force "<X>:\UE\DDC" | Out-Null
   setx UE-LocalDataCachePath "<X>:\UE\DDC"
   ```
   Если шаг 1 показал непустой `UE-ZenDataPath` — он перекроет этот путь; не трогать, сообщить автору.
3. Перезапустить Launcher и терминал, чтобы переменная подхватилась.
4. Записать свободное место на `C:` (до запуска).

**Ничего не удалять.** Если на `C:` уже есть каталоги Zen — только сообщить размер. Очистку решает автор,
и только после остановки `zenserver.exe` и проверки настроек.

## 3. Проект UE_Lab

- Blank, **Blueprint**, **без Starter Content**, в `<X>:\UE_Lab`.
- Сразу после создания, до тяжёлой работы, для HD 620 (Project Settings):
  - Rendering → Dynamic Global Illumination: **None**; Reflection Method: **Screen Space** (Lumen выкл.);
  - Shadow Map Method: **Shadow Maps** (Virtual Shadow Maps выкл.);
  - Nanite оставить, но не включать на мешах.
- Settings → Engine Scalability: **Low**; Editor Preferences → «Use Less CPU when in Background» вкл.
- Если редактор не стартует или падает с ошибкой D3D12 — запуск с `-dx11` (ярлык или
  `UnrealEditor.exe <X>:\UE_Lab\UE_Lab.uproject -dx11`), записать текст ошибки.

## 4. Проверки (результат — автору цифрами)

- В Output Log (или `<X>:\UE_Lab\Saved\Logs\UE_Lab.log`) строки `LogZen` / `LogDerivedDataCache`:
  путь данных Zen на `<X>:`. Процитировать строку.
- Свободное место на `C:` до и после первого открытия проекта (шейдеры компилируются при первом запуске).
- Время первого открытия, FPS пустого уровня во вьюпорте (`stat fps`), загрузка RAM — из Диспетчера задач.

## 5. Unreal MCP

Источник: [Unreal MCP in Unreal Editor (5.8)](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?application_version=5.8).
Плагин экспериментальный.

1. Edit → Plugins: включить **Unreal MCP** и **All Toolsets**, перезапустить редактор.
2. В консоли редактора: `ModelContextProtocol.GenerateClientConfig ClaudeCode`.
3. Запустить Claude Code из корня `UE_Lab`, где создан конфиг. Сервер: `http://127.0.0.1:8000/mcp`.
4. Проверка: Claude Code видит инструменты и, например, создаёт куб на уровне и читает список акторов.

Безопасность: сервер без аутентификации, только localhost. Не открывать порт 8000 наружу,
не менять `DefaultBindAddress`.

## Что коммитить

- В TheLull (ветка `ue-claudeflow`): только отчёт о проверке — запись в `CHANGELOG.md` с цифрами
  (версия, диск, место на `C:` до/после, FPS, работает ли MCP). Без личных путей и логов целиком.
- `UE_Lab` не коммитится. `Content/` хранится локально, резервная копия — на другой накопитель или в облако.
  Git LFS пока не используется.
