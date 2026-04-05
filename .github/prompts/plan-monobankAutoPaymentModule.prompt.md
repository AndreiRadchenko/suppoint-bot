## Plan: Monobank Auto-Payment Module for Telegram Bot

Мета: замінити ручне адмін-підтвердження оплат у боті на миттєве авто-підтвердження через Monobank acquiring webhook, зберігати посилання на квитанцію в БД, підтримати доплату за додатковий час, і винести платіжну частину в перевикористовуваний модуль з уніфікованим API. Рекомендований підхід: інтегрувати легкий HTTP webhook-сервер в той самий процес бота, додати таблицю транзакцій, перевести первинну оплату і доплати на єдиний payment service з ідемпотентною обробкою подій.

**Steps**
1. Фаза 1: Підготовка платіжного каркасу та конфігурації. Створити окремий пакет платіжного модуля (наприклад, services/payments) з публічним інтерфейсом для create_invoice, handle_webhook_event, refresh_status, mark_paid_initial, mark_paid_topup. Додати конфіг-поля для MONO_TEST_TOKEN, MONO_LIVE_TOKEN, MONO_MODE, MONO_WEBHOOK_PATH, MONO_REDIRECT_URL, MONO_USE_TEST, MONO_PUBKEY_CACHE_TTL. *Блокує кроки 2-6.*
2. Фаза 2: Міграція БД під транзакції та квитанції. Додати таблицю payment_transactions (зв’язок з rent і surcharge, тип платежу initial/topup, external_invoice_id, reference, amount_minor, status, receipt_url, raw_payload, paid_at, created_at, updated_at, unique по external_invoice_id). Додати поля для швидкого доступу: у rent — payment_receipt_url, payment_invoice_id; у surcharge — topup_receipt_url, topup_invoice_id. Передбачити індекси на reference/status. *Залежить від 1, блокує 3-6.*
3. Фаза 3: Monobank клієнт і перевірка підпису. Реалізувати HTTP-клієнт для api.monobank.ua: invoice/create, invoice/status, merchant/pubkey. Додати сервіс перевірки X-Sign (ECDSA + SHA-256 по raw body), кешування pubkey і повторну перевірку після ротації ключа. Додати нормалізацію статусів Monobank у внутрішні стани (pending, success, failed, expired). *Залежить від 1-2, блокує 4-6.*
4. Фаза 4: Інтеграція webhook-сервера в процес бота. Додати легкий aiohttp/FastAPI endpoint у тому ж процесі, де працює aiogram polling (окремий async task на старті). Реалізувати обробку webhook: валідація підпису, lookup транзакції за invoiceId/reference, ідемпотентний update, HTTP 200 тільки після успішної фіксації. Врахувати, що expired може не прийти webhook — додати reconciliation job через status endpoint для pending транзакцій. *Залежить від 1-3, блокує 5-6.*
5. Фаза 5: Заміна первинної оплати оренди на авто-підтвердження. У флоу вибору часу оренди формувати invoice через payment module замість поточної схеми зі скріншотом. Надсилати клієнту pageUrl для оплати. Після success webhook: автоматично переводити rent у статус Очікування відкриття, ставити pay_1=OK, оновлювати locker status, зберігати receipt_url. Повністю прибрати ручний approve/reject для первинної оплати з адмін-кнопок, лишивши тільки перегляд історії/діагностики. *Залежить від 1-4, паралельно з 6 частково (UI-частина).*
6. Фаза 6: Авто-підтвердження доплат за додатковий час. У finishRent флоу при нарахуванні доплати створювати topup invoice як окрему транзакцію (payment_type=topup) з прив’язкою до rent/surcharge. Після success webhook: ставити pay_2=OK, зберігати topup receipt_url, завершувати оренду по поточних бізнес-правилах. При failure/expired — давати користувачу повторну оплату через новий invoice. *Залежить від 1-4 і логіки surcharge в існуючих хендлерах.*
7. Фаза 7: Уніфікований API для перевикористання. Винести бізнес-незалежні частини у стабільний фасад (PaymentGateway interface + MonobankProvider + PaymentOrchestrator): ініціація платежу, підтвердження, перевірка статусу, отримання квитанції. Telegram-специфічні дії (повідомлення користувачу, стани FSM) лишити в handlers як адаптер. Це забезпечить перевикористання в майбутньому веб-додатку SUP оренди без переписування Monobank-ядра. *Залежить від 1-6.*
8. Фаза 8: Очищення legacy-логіки і сумісність. Позначити застарілими старі поля payment_file_type/payment_file_id для ручних скріншотів, але тимчасово не видаляти для backward compatibility. Оновити адмін-меню: замість підтвердження оплати показувати моніторинг транзакцій і ручний retry/reconcile. *Залежить від 5-6.*
9. Фаза 9: Тестування та rollout. Додати unit-тести для signature verify, mapping статусів, idempotency; інтеграційні тести для webhook endpoint і DB transitions; sandbox e2e на test token; перевірити перемикання test/live токенів через env. Провести поетапний rollout: спочатку тільки первинні платежі, потім доплати, з метриками помилок webhook/status. *Залежить від усіх попередніх кроків.*

**Relevant files**
- /home/andrii/suppoint-bot/handlers/rent.py — заміна генерації QR/очікування скріншота на створення invoice і запуск payment transaction для первинної оплати.
- /home/andrii/suppoint-bot/handlers/start.py — видалення/спрощення ручних approve callback для pay_1, збереження адмін-огляду і reconcile-дій.
- /home/andrii/suppoint-bot/handlers/finishRent.py — створення topup invoice і авто-фіналізація pay_2 через webhook.
- /home/andrii/suppoint-bot/db.py — додавання CRUD для payment_transactions, збереження receipt URL/invoice ID, ідемпотентні update-операції.
- /home/andrii/suppoint-bot/bot.py — запуск додаткового HTTP сервера/webhook task поруч з polling і scheduler.
- /home/andrii/suppoint-bot/create_bot.py — якщо потрібно, спільні залежності/ініціалізація сервісів для handlers і webhook.
- /home/andrii/suppoint-bot/config_data/config.py — нові env-параметри Mono (test/live, mode, webhook path, redirect, pubkey cache).
- /home/andrii/suppoint-bot/.env — test/live токени вже є; доповнити режимом і URL-параметрами.
- /home/andrii/suppoint-bot/monobank-acquiring/webhook.md — референс для перевірки X-Sign і політики pubkey cache.
- /home/andrii/suppoint-bot/monobank-acquiring/invoice.md — референс для create/status/cancel/finalize при потребі.

**Verification**
1. Юніт-тест: валідний X-Sign приймається, невалідний відхиляється; сценарій ротації pubkey проходить.
2. Юніт-тест: повторний webhook для тієї ж транзакції не дублює зміну статусу rent/surcharge (ідемпотентність).
3. Інтеграційний тест: create invoice з test token повертає invoiceId/pageUrl і створює pending запис у payment_transactions.
4. Інтеграційний тест: webhook success переводить первинну оплату у pay_1=OK + status Очікування відкриття + locker update + receipt_url в БД.
5. Інтеграційний тест: webhook success для topup переводить pay_2=OK і завершує доплату.
6. Інтеграційний тест: failure/expired залишає оренду в очікуванні оплати або дає retry без розблокування.
7. E2E sandbox: користувач у Telegram отримує pageUrl, оплачує, і бот без адміна миттєво надсилає підтвердження доступу до комірки.
8. E2E sandbox: сценарій доплати після прострочки оплати часу працює автоматично і зберігає квитанцію.
9. Регресійна перевірка: відкриття комірки, таймер оренди, завершення оренди та повідомлення не ламаються.

**Decisions**
- Webhook сервер розміщується в тому ж процесі бота (single deploy).
- Авто-підтвердження застосовується і для первинної оплати, і для доплат за додатковий час.
- Основна модель зберігання: окрема таблиця payment_transactions + денормалізовані receipt/invoice поля в rent/surcharge.
- Після успішної оплати доступ до відкриття комірки вмикається одразу (без додаткової ручної валідації).

**Further Considerations**
1. Міграції SQLite. Рекомендація: додати versioned SQL-міграції (папка migrations) замість ad-hoc ALTER у коді, щоб стабільно деплоїти оновлення.
2. Надійність webhook у проді. Рекомендація: публічний HTTPS endpoint + retry-safe логування подій + алертинг на зростання pending старше N хв.
3. Перевикористання в web app. Рекомендація: тримати Monobank adapter і PaymentOrchestrator без Telegram-залежностей, а бот/веб інтегрувати через окремі thin adapters.
