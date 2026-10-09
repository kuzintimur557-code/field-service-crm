# Field Service CRM Changelog

## 0.3.0
- AI Inbox: приём писем (JSON и сырые .eml), дедупликация, разбор телефона/адреса/даты/услуги, черновик заявки с подтверждением менеджером, подсказка свободных окон и назначение исполнителя
- AI Calls: автоматический анализ звонков — настроение клиента, признаки продажи, follow-up; авто-статус «Нужен контакт»; данные из текста звонка в черновике заявки
- Голосовой помощник: страница «Голос» (`/voice`) для владельца и менеджера на любой подписке; большая кнопка на главной; одна кнопка «Отправить помощнику» сама определяет намерение (заявка / поиск / напоминание / заметка); распознавание в браузере (Web Speech API, ru-RU)
- SaaS: тарифы, лимиты, подписки и пробный период (14 дней), cron-напоминания, ограничение изменений при просрочке
- A3 Мастер: упрощённый режим частного мастера — экран «Сегодня» и голосовой ввод
- Onboarding первого запуска (чек-лист из 5 шагов)
- PWA: иконки, офлайн-кэш, установка на телефон
- Mobile: таблицы с горизонтальной прокруткой, единый стиль полей, ₽ после суммы, единая кнопка «Назад», исправлены переполнения форм
- Производительность: индексы основных таблиц, SQLite WAL, лимиты списков, фоновая отправка Telegram, сокращение записей last_seen, агрегация финансов и дашборда без N+1
- Безопасность: bcrypt для демо-учёток, /debug только для superadmin, rate-limit логина без обхода через XFF, закрыта stored XSS в графе A3
- Архитектура: декомпозиция монолита — 19 доменных роутеров в app/routes, слои deps/common/uploads/plans/billing, Alembic-миграции; main.py 48.9k → 20.4k строк
- Инфраструктура разработки: GitHub Codespaces (`.devcontainer/`), скрипт туннеля `scripts/dev_tunnel.sh`

## 0.2.2
- Public `/health` endpoint
- Public `/ready` endpoint
- Request id observability
- HTTP error logging
- System deployment diagnostics
- Localized 404/405 pages
- Safe build metadata
- GitHub Actions CI
- Expanded `.gitignore`
- Production environment example
- Production launch checklist
- README

## 0.2.1
- Admin Center
- Production checklist
- Roadmap
- Production notes
- Login audit
- Failed login attempts
- Brute-force protection
- Password hashing
- Profile password change
- Team password management
- Duplicate users cleanup
- Dashboard cleanup
- Ruble currency

## 0.2.0
- Роли: boss / manager / worker
- Исполнитель вместо монтажника
- Фото до/после
- PDF акт
- PDF счёт
- Внутренний чат заявки
- Activity timeline
- Архив заявок
- Клиенты
- История клиента
- Каталог услуг и материалов
- Смета в заявке
- Финансы
- CSV экспорт
- Настройки компании
- Тарифные функции
- Billing page
- Заглушка 1С
- Заглушка звонков
- Backup
- Debug
- System status
- Favicon
- Shared CSS
