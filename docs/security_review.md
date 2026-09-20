# Production security review

Дата проверки: 20 сентября 2026 года.

## Результат

Проверены HTTP-границы FastAPI-приложения, аутентификация и сессии,
tenant-доступ, загрузки, production-конфигурация, хранение секретов и Python-зависимости.
Найденные критичные для запуска проблемы устранены. Security smoke и полный CRM smoke
проходят на чистом окружении зависимостей; PostgreSQL-набор указан в разделе проверки.

Статус по уровням риска:

| Уровень | Найдено | Исправлено | Осталось |
|---|---:|---:|---:|
| Critical | 0 | 0 | 0 |
| High | 4 | 4 | 0 |
| Medium | 4 | 4 | 0 |
| Low / hardening | 3 | 0 | 3 |

## Исправленные находки

### SEC-001 — бессрочные и неотзываемые сессии

- **Риск:** High.
- **Где:** `app/main.py`, функции `sign_session_value`, `verify_session_value` и `get_user`.
- **До исправления:** cookie содержала только подписанное имя пользователя. Похищенная cookie
  оставалась действительной после смены пароля и не имела серверного срока жизни.
- **Исправление:** формат `v1` теперь включает время выпуска и `session_version`, срок жизни
  ограничен семью днями, подпись сравнивается через HMAC, а смена или сброс пароля повышает
  версию сессии и отзывает ранее выпущенные cookie.
- **Проверка:** `tests/smoke_security.py` проверяет валидную, просроченную, изменённую и
  отозванную сессию.
- **Статус:** исправлено.

### SEC-002 — межсайтовые state-changing запросы

- **Риск:** High.
- **Где:** `app/security.py`, `get_cross_site_request_error`; `app/main.py`,
  `security_headers_middleware`.
- **До исправления:** POST/PUT/PATCH/DELETE полагались только на `SameSite=Lax` cookie.
- **Исправление:** middleware отклоняет `Sec-Fetch-Site: cross-site`, чужие `Origin` и
  `Referer`; production origins задаются через `APP_BASE_URL` и
  `CSRF_TRUSTED_ORIGINS`. Запросы cron и API без browser-заголовков остаются совместимыми.
- **Проверка:** security smoke проверяет разрешённые и запрещённые origins и фактический
  ответ middleware `403`.
- **Статус:** исправлено.

### SEC-003 — небезопасная production-конфигурация HTTP

- **Риск:** High.
- **Где:** `app/security.py`; создание `FastAPI` и `TrustedHostMiddleware` в
  `app/main.py`.
- **До исправления:** слабый `SECRET_KEY` мог попасть в production, OpenAPI был публичен,
  Host header не ограничивался.
- **Исправление:** production startup завершается ошибкой без секрета от 32 символов,
  разрешённых доменов и Secure session cookie; `/docs`, `/redoc` и `/openapi.json`
  отключаются; Host проверяется
  по `TRUSTED_HOSTS`; добавлены CSP, HSTS, COOP, CORP и запрет кэширования динамических
  ответов.
- **Проверка:** `tests/smoke_production_security.py` запускает приложение в production,
  проверяет закрытую документацию, отклонение чужого Host и защитные заголовки.
- **Статус:** исправлено.

### SEC-004 — опасный prototype-код авторизации и заявок

- **Риск:** High при случайном подключении роутеров.
- **Где:** удалённые `app/routes/auth.py` и `app/routes/tasks.py`.
- **До исправления:** в репозитории оставались пароли `1234`, API без авторизации и запись
  загруженных файлов без ограничений. Эти роутеры не были подключены к рабочему приложению,
  но создавали опасный путь для будущего импорта.
- **Исправление:** неиспользуемые prototype-модули удалены; smoke проверяет, что они не
  вернулись.
- **Статус:** исправлено.

### SEC-005 — загрузки и размер HTTP-запросов без ограничений

- **Риск:** Medium.
- **Где:** `app/main.py`, `validate_upload_file`; `app/security.py`,
  `get_request_size_error`.
- **До исправления:** сервер принимал файлы без общего лимита и местами доверял
  присланному `Content-Type`.
- **Исправление:** изображения ограничены 10 MiB, клиентские файлы 25 MiB, записи звонков
  50 MiB, расширения проверяются по allowlist, сохраняемый MIME определяется сервером,
  общий заявленный размер запроса ограничен 60 MiB.
- **Проверка:** smoke проверяет запрещённое расширение, превышение размера, отрицательный и
  некорректный `Content-Length`.
- **Статус:** исправлено.

### SEC-006 — подмена IP для обхода login rate limit

- **Риск:** Medium.
- **Где:** `app/main.py`, `get_request_ip`.
- **До исправления:** первый адрес из `X-Forwarded-For` принимался от любого клиента.
- **Исправление:** proxy-заголовок используется только при `TRUST_PROXY_HEADERS=1` или в
  Railway-окружении; адрес валидируется как IPv4/IPv6, логин и IP нормализуются по длине.
- **Проверка:** security smoke подтверждает, что spoofed header игнорируется без доверия к
  proxy.
- **Статус:** исправлено.

### SEC-007 — слабая парольная политика

- **Риск:** Medium.
- **Где:** `app/main.py`, `is_password_strong` и `verify_password`.
- **До исправления:** принимались любые пароли длиной от шести символов.
- **Исправление:** минимум восемь символов, хотя бы одна буква и цифра, верхняя граница
  72 UTF-8 байта для корректной работы bcrypt; интерфейс показывает новое требование.
- **Проверка:** security smoke покрывает допустимые и недопустимые варианты и безопасную
  обработку слишком длинного bcrypt-ввода.
- **Статус:** исправлено.

### SEC-008 — неограниченные версии runtime-зависимостей

- **Риск:** Medium.
- **Где:** `requirements.txt`, `.github/workflows/ci.yml`.
- **До исправления:** восемь прямых зависимостей устанавливались без нижней и верхней
  границы, поэтому сборка могла незаметно измениться.
- **Исправление:** для всех прямых зависимостей заданы совместимые диапазоны; минимальная
  версия `python-multipart` поднята до `0.0.31`, где исправлена обработка отрицательного
  `Content-Length`; CI выполняет `python -m pip check`.
- **Проверка:** чистое Python 3.10 окружение собрано из `requirements.txt`; `pip check`,
  `pip-audit -r requirements.txt` и все smoke-тесты прошли. На дату аудита известных
  уязвимостей в установленном наборе не найдено.
- **Статус:** исправлено.
- **Источники:** [python-multipart advisory GHSA-v9pg-7xvm-68hf](https://github.com/advisories/GHSA-v9pg-7xvm-68hf),
  [python-multipart на PyPI](https://pypi.org/project/python-multipart/).

## Остаточные риски и следующий hardening

1. **CSP допускает inline script/style (Low).** Шаблоны содержат встроенные скрипты и
   стили, поэтому политика пока использует `'unsafe-inline'`. Следующий шаг — вынести их в
   static-файлы или внедрить nonce, затем убрать это разрешение.
2. **Проверка содержимого файлов (Low).** Allowlist расширений и серверный MIME снижают
   риск, но не заменяют проверку magic bytes и антивирус. Для внешнего файлового обмена
   нужен scanner/quarantine перед выдачей файла пользователю.
3. **Chunked request body (Low).** Приложение ограничивает `Content-Length`, а каждый
   upload дополнительно проверяет фактический размер временного файла. На ingress/reverse
   proxy следует также задать жёсткий лимит тела 60 MiB, чтобы отклонять chunked body до
   Python-процесса.

## Проверка блока

```bash
python -m pip check
python -m compileall -q app tests scripts
python tests/smoke_security.py
python tests/smoke_production_security.py
python tests/smoke_object_storage.py
python tests/smoke_background_jobs.py
python tests/smoke_error_monitoring.py
python tests/smoke_app.py
python tests/smoke_postgresql.py
python tests/smoke_postgresql_migration.py
python tests/smoke_postgresql_concurrency.py
python tests/smoke_postgresql_backup.py
```

Перед production-допуском также выполнить backup/restore drill и проверить readiness на
`/platform/readiness` с реальными доменом, secret и proxy-настройками.
