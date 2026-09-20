# CI/CD и production release gate

## Поток релиза

1. Push или pull request в `main` запускает `.github/workflows/ci.yml`.
2. Параллельно выполняются:
   - аудит production-зависимостей через `pip-audit`;
   - полный SQLite/security smoke;
   - schema, migration, concurrency, backup/restore и полный smoke на PostgreSQL 16.
3. Job `Production release gate` становится зелёным только после успеха всех трёх веток.
4. Railway GitHub Autodeploy с включённым **Wait for CI** начинает production deploy
   только после успешного завершения workflow.
5. Railway проверяет `/health` до переключения трафика на новую версию.
6. После события успешного production deployment workflow
   `.github/workflows/post-deploy.yml` запускает live-проверку.

Live-проверка подтверждает:

- `/health` и `/ready` отвечают `200` и `ok: true`;
- опубликован именно ожидаемый commit;
- активный production database backend — PostgreSQL;
- `/docs`, `/redoc` и `/openapi.json` закрыты;
- cross-site POST блокируется;
- CSP, `X-Frame-Options`, `nosniff` и `Cache-Control` присутствуют.

## Однократная настройка GitHub и Railway

В Railway для production web-service:

1. Source — этот GitHub repository, deploy branch — `main`.
2. Включить **Wait for CI**.
3. Healthcheck Path — `/health`, timeout — `300` секунд.
4. Restart Policy — `ON_FAILURE`.
5. Убедиться, что production variables из
   `docs/production_launch_checklist.md` заданы.

Railway отправляет healthcheck с Host `healthcheck.railway.app`; приложение добавляет
его в trusted hosts только внутри Railway-окружения.

В GitHub:

1. Сделать `Production release gate` обязательной status check для `main`.
2. Если Railway deployment event не содержит `environment_url`, создать repository
   variable `PRODUCTION_BASE_URL` с публичным HTTPS URL.
3. Не добавлять database, S3 или application secrets в workflow: live-проверка использует
   только публичные endpoints и deployment metadata.

## Локальная проверка

```bash
python3 tests/smoke_release.py
python3 scripts/check_deployment.py \
  --base-url https://crm.example \
  --expected-commit COMMIT_SHA \
  --expected-database-backend postgresql
```

Для локального HTTP разрешён только явный флаг `--allow-http`.

## Сигнал остановки и rollback

Deploy нельзя продолжать, если release gate красный. Если post-deploy workflow упал:

1. сверить commit в `/health` с deployment SHA;
2. проверить `/ready` и Railway runtime logs;
3. вернуть последнюю рабочую deployment через Railway Rollback;
4. исправить причину и провести новый обычный релиз через CI.

Не запускать повторный deploy поверх неизвестного состояния только ради перезапуска.
