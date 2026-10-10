# Деплой на VPS (Docker)

Быстрый запуск платформы на любом VPS с Docker. Пример — Ubuntu 22.04+,
Timeweb/Beget/Selectel, минимум 1 CPU / 1 ГБ RAM / 10 ГБ диск.

## 1. Подготовка сервера

```bash
# на сервере
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER   # перелогиниться после
```

Откройте порт 8000 (или настройте nginx/caddy как reverse proxy с HTTPS —
рекомендуется, см. раздел «Домен и HTTPS»):

```bash
sudo ufw allow 8000/tcp
```

## 2. Клонирование и запуск

```bash
git clone https://github.com/kuzintimur557-code/field-service-crm.git
cd field-service-crm

cp .env.example .env
nano .env   # обязательно заполнить секции ниже
```

Обязательные переменные в `.env`:

```
ENV=production
SECRET_KEY=<длинная случайная строка, 32+ символов>
COOKIE_SECURE=1
TRUSTED_HOSTS=your-domain.example
AUTOMATION_CRON_SECRET=<длинная случайная строка>
INBOX_WEBHOOK_SECRET=<длинная случайная строка>
BOT_TOKEN=...        # если нужны Telegram-уведомления
CHAT_ID=...
```

Запуск:

```bash
docker compose up -d --build
docker compose logs -f app   # дождаться "Uvicorn running"
```

Проверка: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.
Вход: `boss` / `boss123` (демо-учётки; сразу сменить в «Ещё → Команда»).

## 3. Cron-задания на сервере

```bash
crontab -e
```

```
*/1 * * * * curl -s -X POST -H "x-automation-secret: $SECRET" http://127.0.0.1:8000/automation/cron/background-jobs
0 3 * * *   curl -s -X POST -H "x-automation-secret: $SECRET" http://127.0.0.1:8000/automation/cron/database-backup
0 9 * * *   curl -s -X POST -H "x-automation-secret: $SECRET" http://127.0.0.1:8000/automation/cron/subscription-reminders
```

## 4. Бэкапы

Дампы лежат в volume `app-data/backups` и зеркалируются в S3 при настроенном
`OBJECT_STORAGE_BACKEND=s3`. Для надёжности подключите S3 (любой
S3-compatible: Timeweb, Selectel, Yandex Object Storage).

## 5. Домен и HTTPS (nginx)

```nginx
server {
    listen 80;
    server_name your-domain.example;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example
```

После выпуска сертификата добавьте в `.env`: `TRUST_PROXY_HEADERS=1`,
перезапустите: `docker compose up -d`.

## 6. Переход на PostgreSQL (по желанию)

1. `docker compose --profile postgres up -d db`
2. На время миграции остановите app: `docker compose stop app`
3. Выполните согласованную миграцию (см. `docs/postgresql_migration.md`,
   скрипт `scripts/migrate_sqlite_to_postgresql.py`).
4. В `.env`: `DATABASE_BACKEND=postgresql`,
   `DATABASE_URL=postgresql://crm:<пароль>@db:5432/crm`,
   `POSTGRESQL_EXPERIMENTAL=1`
5. `docker compose up -d` — app поднимется на PostgreSQL.

Подробности и проверки: [Production Launch Checklist](production_launch_checklist.md).
