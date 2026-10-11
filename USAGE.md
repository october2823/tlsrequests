# YumeTlsClient / tlsrequests

## Установка и сборка

Для текущей платформы нужна shared library из Go cgo. На Windows установите Go 1.24+ и MinGW-w64, затем из корня репозитория:

```powershell
$env:CGO_ENABLED = "1"
$env:CC = "x86_64-w64-mingw32-gcc"
go -C native build -buildmode=c-shared -o ../tlsrequests/tlsrequests.dll .
python -m pip install -e .
```

Linux/macOS: соберите `tlsrequests.so` или `tlsrequests.dylib` из `native/` через `go build -buildmode=c-shared`; для cgo нужен системный C-компилятор. Бинарники платформенные, их нельзя переносить между ОС/архитектурами. Если файл хранится отдельно, задайте `TLSREQUESTS_LIBRARY`.

## Запросы

```python
import asyncio
from tlsrequests import Session, Profiles

async def main():
    async with Session(client_identifier=Profiles.CHROME_152, timeout=20) as session:
        session.headers.update({"Accept": "application/json"})
        response = await session.get("https://example.com", params={"page": 1})
        print(response.status_code, response.http_version, response.elapsed)

asyncio.run(main())
```

Все сетевые вызовы — async: используйте `await session.get(...)`, `await session.post(...)` и `async with`. Методы поддерживают `params`, `data`, `json`, `files`, `headers`, `cookies`, `timeout`, `proxy`, `allow_redirects`, `header_order` и `host_override`.

## Multipart

```python
async with Session() as session:
    response = await session.post(
        "https://example.com/upload",
        data=[("key", "uploads/42"), ("policy", "..." )],
        files=[("file", ("blob", pdf_bytes, "application/pdf"))],
    )
```

`data` и `files` принимают mapping или последовательность пар; последовательности сохраняют порядок частей. Multipart кодировщик создаёт CRLF-разделители и `----WebKitFormBoundary` с 16 hex-символами. Доступна функция `encode_multipart`.

## Профили и transport

`ALL_IDENTIFIERS`, `ClientIdentifier`, `Profiles` и `find(prefix)` построены по отображению профилей upstream v1.16.0. `Session` проверяет идентификатор при создании и предлагает близкие варианты. Текущий default — Chrome 152.

`http_version` принимает `None`/`"auto"`, `1`/`"1.1"`/`"h1"`, `2`/`"h2"`, `3`/`"h3"`/`"quic"`. HTTP/3 использует upstream protocol racing, а не режим только-H3; при прокси для HTTP/3 нужен SOCKS5. `Response.http_version` сообщает версию по `used_protocol`, а `Response.used_protocol` сохраняет строку Go.

Transport-атрибуты можно менять между вызовами; следующий вызов создаёт новую Go-сессию. `await session.reset_connection()` принудительно заменяет идентификатор Go-сессии и инициирует новое соединение. `AsyncSession.configure_executor(n)` задаёт общий пул до начала запросов.

## Cookies и response

`session.cookies` — `CookieJar`, ключ куки `(name, domain, path)`. Есть `set`, `update`, `load`, `get`, `get_cookie`, `remove`, `clear_domain`, `export`, `to_dict`. `Response` предоставляет `status_code`, `text`, `content`, `headers`, `cookies`, `history`, `elapsed`, `json()`, `raise_for_status()`.

## Текущие ограничения

`stream=True` не реализован; тело читается целиком в память. Upstream CFFI не возвращает полную цепочку redirect history, поэтому `history` пока пуст. Пользовательский JA3 принимает поля схемы upstream CFFI; автоматическое заполнение остальных полей Chrome fingerprint требует поддержки адаптера и должно быть проверено отдельно. `http_version="3"` включает upstream racing, победивший протокол зависит от хоста и доступности QUIC. Проект пока не публиковать в PyPI до CI-сборки целевых платформ и проверки Go-адаптера.
