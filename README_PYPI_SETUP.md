# Первая публикация на PyPI

Проект `yumeclient` готов к публикации, но требуется одноразовая настройка:

## Проблема
PyPI trusted publisher не может создать новый проект автоматически. Нужно:

1. Зайти на https://pypi.org/manage/account/publishing/
2. Создать "pending publisher" для:
   - Project name: `yumeclient`
   - Owner: `october2823`
   - Repository: `yumeclient`
   - Workflow: `release.yml`
   - Environment: `pypi`

3. Затем запустить workflow вручную или создать новый release

## Альтернатива (если pending publisher уже есть)
Проверить точное совпадение имён в:
- pyproject.toml: `name = "yumeclient"`
- PyPI pending publisher: должно быть `yumeclient` (без заглавных букв)

После первой успешной публикации все последующие releases будут публиковаться автоматически.
