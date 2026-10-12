# YumeTlsClient / yumeclient

## Установка

Для полноценного `pip install` нужен wheel под ОС и архитектуру. В релизном workflow wheels собираются отдельно для Windows, Linux и macOS и содержат Go shared library. После настройки PyPI Trusted Publishing и создания GitHub Release их можно установить так:

```sh
python -m pip install yumeclient
```

Для локальной сборки нужны Go 1.24+, cgo и C-компилятор. Windows также требует MinGW-w64:

```powershell
$env:CGO_ENABLED = "1"
$env:CC = "x86_64-w64-mingw32-gcc"
go -C native build -buildmode=c-shared -o ../yumeclient/yumeclient.dll .
python -m pip install -e .
```

Linux/macOS: `sh scripts/build-native.sh`, затем `python -m pip install -e .`. Shared library строится под текущую платформу, отдельно для каждой ОС/архитектуры.

## Запросы

```python
import asyncio
from yumeclient import Session, Profiles

async def main():
    async with Session(client_identifier=Profiles.CHROME_152, timeout=20) as session:
        session.headers.update({"Accept": "application/json"})
        response = await session.get("https://example.com", params={"page": 1})
        print(response.status_code, response.http_version, response.elapsed)

asyncio.run(main())
```

Методы `get`, `post`, `put`, `patch`, `delete`, `head` асинхронные: вызывайте их с `await`. Доступны `params`, `data`, `json`, `files`, `headers`, `cookies`, `timeout`, `proxy`, `allow_redirects`, `header_order` и `host_override`.

## Multipart

```python
async with Session() as session:
    response = await session.post(
        "https://example.com/upload",
        data=[("key", "uploads/42"), ("policy", "...")],
        files=[("file", ("blob", pdf_bytes, "application/pdf"))],
    )
```

Mapping или последовательность пар принимаются для полей/файлов. Последовательности сохраняют порядок частей. Кодировщик создаёт CRLF-разделители и Chrome-подобную границу `----WebKitFormBoundary` плюс 16 hex-символов. Функция `encode_multipart` доступна для отдельного использования.

## Профили и протоколы

`ALL_IDENTIFIERS`, `ClientIdentifier`, `Profiles` и `find(prefix)` соответствуют таблице профилей upstream v1.16.0. Неизвестный профиль вызывает `SessionConfigurationError` с похожими вариантами. Default — `chrome_152`.

`http_version` принимает `None`/`"auto"`, `1`/`"1.1"`/`"h1"`, `2`/`"h2"`, `3`/`"h3"`/`"quic"`. В upstream HTTP/3 включается через racing с HTTP/2; это не режим «только h3». Через прокси HTTP/3 разрешён только с SOCKS5. `Response.http_version` нормализует протокол, `Response.used_protocol` сохраняет исходное значение Go.

Transport-атрибуты можно менять перед запросом; изменение создаёт новую Go-сессию. `await session.reset_connection()` принудительно заменяет сессию. `AsyncSession.configure_executor(n)` настраивает общий пул до старта запросов.

## Cookies и response

`session.cookies` — `CookieJar` с идентичностью `(name, domain, path)`. Методы: `set`, `update`, `load`, `get`, `get_cookie`, `remove`, `clear_domain`, `export`, `to_dict`. `Response` предоставляет `status_code`, `text`, `content`, `headers`, `cookies`, `history`, `elapsed`, `json()` и `raise_for_status()`.

## Ограничения

`stream=True` не поддерживается: ответ целиком буферизуется в памяти. Upstream CFFI не отдаёт redirect history, поэтому `history` пока пуст. Автодополнение custom JA3 из Chrome defaults не реализовано — передавайте поддерживаемые поля через схему upstream. Для некоторых профилей нет браузерно-точных HTTP/3 настроек; при запросе HTTP/3 используются параметры upstream по умолчанию. Публикация выполняется только после успешных CI-сборок и настройки Trusted Publishing в PyPI.
