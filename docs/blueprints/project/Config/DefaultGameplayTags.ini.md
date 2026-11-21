# DefaultGameplayTags.ini — конфигурация тегов F00

**Mirror:** `docs/blueprints/project/Config/DefaultGameplayTags.ini.md` → **real target:** `<ProjectRoot>/Config/DefaultGameplayTags.ini`.
**Тип:** один проектный конфигурационный файл, **не** Blueprint. **Статус:** planned; существующее содержимое локального ini не исследовано.

## Перед изменением
Claude Code через текущий Unreal MCP/доступ к файлам должен сначала **прочитать имеющийся** `Config/DefaultGameplayTags.ini` и проверить Project Settings → Gameplay Tags → Import Tags From Config. Нельзя заменять чужой файл целиком или удалять имеющиеся tags.

## Добавляемые записи / минимальный контракт
- `Time.Advance.Realtime`
- `Time.Advance.Action`
- `Time.Advance.Sleep`
- `Time.Advance.Debug`

Предпочтительно создать через **Project Settings → Gameplay Tags → Manage Gameplay Tags** с сохранением в правильный источник `.ini`; результат, сгенерированный редактором, считать эталоном синтаксиса и записать в backlog, а не прописывать неподтверждённые секции по памяти. Не создавать tags для систем, которых ещё нет.

## Проверка
После сохранения в установленном UE 5.8.4: теги выбираются в pin `Reason: Gameplay Tag`, сохраняются после закрытия и повторного открытия проекта; ни один существующий tag не пропал. Зафиксировать фактический diff ini.

**Первичные источники Epic 5.8:** [Using Gameplay Tags](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-gameplay-tags-in-unreal-engine), [UGameplayTagsSettings](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/GameplayTags/UGameplayTagsSettings?application_version=5.8).
