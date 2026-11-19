# Локальная установка UE 5.8 — инструкция для Claude Code на машине автора

Первая задача локального Claude Code. Windows. Движок и проект — на внешнем USB 3.0 диске (400 ГБ),
на внутреннем диске свободно ~20 ГБ: туда **ничего тяжёлого** не пишем.

Ниже буква внешнего диска — `E:`. Перед работой узнай настоящую букву у автора и подставь её.

## Почему кэш нельзя оставлять на внутреннем диске

С UE 5.4 локальный DDC хранит Zen, по умолчанию в `C:\ProgramData\Epic\Zen\Data\`.
Источник: [Using Derived Data Cache](https://dev.epicgames.com/documentation/unreal-engine/using-derived-data-cache-in-unreal-engine).
DDC растёт до десятков гигабайт (шейдеры, текстуры, меши) — 20 ГБ закончатся на первом шаблонном проекте.
Поэтому DDC идёт на внешний диск: USB 3.0 медленнее, но лучше медленный кэш, чем полный системный диск.

## Шаги

1. **Launcher.** Установить UE 5.8 (последний hotfix — проверить у автора, ожидается 5.8.4)
   в `E:\Epic\UE_5.8`. В Launcher → Settings: «Edit Vault Cache Location» → `E:\Epic\VaultCache`.
   Компоненты ставить минимально: без Android/iOS/Linux target, без Debug symbols (экономит десятки ГБ).
2. **DDC — до первого запуска редактора** (иначе Zen успеет начать писать на `C:`):
   ```powershell
   New-Item -ItemType Directory -Force E:\UE\DDC | Out-Null
   setx UE-LocalDataCachePath "E:\UE\DDC"
   ```
   Перезапустить Launcher/терминал, чтобы переменная подхватилась. Zen создаст `E:\UE\DDC\Zen`.
3. **Проект** — на внешнем диске, рядом с репозиторием: `E:\TheLull` (клон `Nolavel/TheLull`,
   ветка `ue-claudeflow`). `Intermediate/`, `Saved/`, `DerivedDataCache/` проекта тоже окажутся на `E:`.
4. **Проверка** (обязательна, результат — автору):
   - первый запуск редактора, затем в Output Log найти строки `LogDerivedDataCache` / `LogZen`:
     путь данных должен быть на `E:`;
   - `C:\ProgramData\Epic\Zen\Data\` не растёт (размер до и после запуска);
   - свободное место на `C:` до и после — записать цифры.
5. **Если `C:` всё равно занят** — Editor Preferences → General → Global → Local DDC Path → `E:\UE\DDC`,
   закрыть редактор, удалить `C:\ProgramData\Epic\Zen\Data\`, повторить проверку.

## Что коммитить сегодня

Репозиторий публичный, бесплатный Git LFS на GitHub ограничен, политика для бинарных `.uasset` ещё не решена.
Поэтому **сегодня в git — только текст**:

- `.gitignore` (уже в репозитории);
- если автор создаёт проект: `TheLull.uproject`, `Config/`, `Source/` (если C++);
- запись в `CHANGELOG.md`: версия движка, буквы дисков, цифры свободного места до/после.

**Не коммитить:** `Content/` (пока не решён LFS), сам движок, `Intermediate/`, `Saved/`, `Binaries/`,
`DerivedDataCache/`, логи с личными путями.

Ветка — `ue-claudeflow`. Перед работой `git pull` (облачный Claude тоже пишет в неё), push — сам, после проверки.

## Открытые вопросы автору

- Буква внешнего диска.
- Создаём ли сегодня пустой проект, и какой шаблон (Blank C++ или Blueprint).
- Политика для `Content/`: Git LFS, отдельное хранилище или пока только локально.
