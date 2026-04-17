# ha_bot

'available', 'rented', 'reserved', 'maintenance'
«доступний», «орендований», «зарезервований», «обслуговування»

'available' - доступний
'in_process' - користувач оформлюж
'on_inspection' - оічкує перевірку


rental_started - оренду розпочато

## Project Analysis: `ha_bot` — SUP Board Rental Telegram Bot

---
venv: 
```bash
sudo apt-get install -y python3 python3-pip python3-venv
sudo ln -s /usr/bin/python3 /usr/local/bin/python
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
source .venv/bin/activate
python bot.py
```

to kill process:
```bash
pgrep -af "python.*bot.py|watchmedo.*bot.py" || true
kill 62514 && echo "Stopped process 62514"

pgrep -af "python.*bot.py|watchmedo.*bot.py" || echo "No bot process running"
kill -9 62514 && echo "Force-stopped process 62514"
```

in development, setup watchdog to restart bot on code change:
```bash
pip install watchdog
watchmedo auto-restart --patterns="*.py" --recursive -- python bot.py
```

## Run in background with systemd

Use prepared service files from this repository:
- `deploy/systemd/suppoint-bot.service` — production mode
- `deploy/systemd/suppoint-bot-dev.service` — development mode with auto-restart on `*.py` changes

Install service files:
```bash
sudo cp deploy/systemd/suppoint-bot.service /etc/systemd/system/
sudo cp deploy/systemd/suppoint-bot-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Production service (recommended on server):
```bash
sudo systemctl enable suppoint-bot
sudo systemctl start suppoint-bot
sudo systemctl status suppoint-bot
journalctl -u suppoint-bot -f
```

Development autoreload service (watchdog):
```bash
source .venv/bin/activate
pip install watchdog

sudo systemctl enable suppoint-bot-dev
sudo systemctl start suppoint-bot-dev
sudo systemctl status suppoint-bot-dev
journalctl -u suppoint-bot-dev -f
```

Service management:
```bash
sudo systemctl restart suppoint-bot
sudo systemctl stop suppoint-bot
sudo systemctl disable suppoint-bot

sudo systemctl restart suppoint-bot-dev
sudo systemctl stop suppoint-bot-dev
sudo systemctl disable suppoint-bot-dev
```

Notes:

- No need to run `source .venv/bin/activate` for normal service starts.
- Auto-start after server reboot is handled by `systemctl enable`.
- Auto-restart after crash is handled by `Restart=always`.
- Dependencies must be installed in the same venv used by the service (`/home/andrii/suppoint-bot/.venv`).
- After any `requirements.txt` update, run install again and restart the service.

Install/refresh dependencies for the service venv:
```bash
cd /home/andrii/suppoint-bot
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart suppoint-bot
```

If you use `suppoint-bot-dev.service`, make sure `watchdog` is installed in the same venv:
```bash
cd /home/andrii/suppoint-bot
source .venv/bin/activate
pip install watchdog
sudo systemctl restart suppoint-bot-dev
```

Docker:
```bash
docker run --rm -it --env-file .env suppoint-bot
```

## What It Is

A **Telegram bot for SUP (Stand-Up Paddleboard) rental management** integrated with Home Assistant for IoT smart locker control. The bot handles the complete rental lifecycle — from user registration and locker booking to payment verification, equipment tracking, and return with surcharge calculation. All UI text is in Ukrainian.

---

## Frameworks & Tools

| Category | Tool | Purpose |
|---|---|---|
| **Bot Framework** | `aiogram 3.x` | Async Telegram bot (routers, FSM, keyboards) |
| **HTTP (async)** | `aiohttp` | Home Assistant API calls |
| **HTTP (sync)** | `requests` | HA switch toggle commands |
| **Database** | `sqlite3` | Persistent storage |
| **Scheduler** | `apscheduler` | Background timer every 15 seconds |
| **Config** | `environs` | Environment variable loading |
| **Export** | `pandas` + `openpyxl` | Excel report generation |
| **Language** | Python 3 (asyncio) | Runtime |

**Dependencies to install**:
```bash
pip install -r requirements.txt
```

---

## Project Structure

```
ha_bot-main/
│
├── bot.py                  # Entry point — starts bot + scheduler concurrently
├── create_bot.py           # Bot/Dispatcher init, MemoryStorage for FSM
├── db.py                   # Database class — 51 methods covering all DB ops
├── ha_bot.db               # SQLite database (committed to repo)
│
├── config_data/
│   └── config.py           # Dataclasses + env var loader (BOT_TOKEN, ADMINS, HA_URL, HA_TOKEN)
│
├── handlers/               # Telegram router handlers (feature modules)
│   ├── start.py            # Main menu, admin panel, locker control, My Rentals
│   ├── rent.py             # Rental booking FSM flow
│   ├── finishRent.py       # Rental completion + surcharge FSM flow
│   ├── req.py              # User registration FSM flow
│   └── error_report.py     # Support ticket FSM flow
│
├── helper/
│   ├── helper.py           # Logging, message cleanup, HA state reader
│   └── utilits_funk.py     # Background timer — processes all active rentals every 15s
│
├── kb/kb.py                # All inline keyboard definitions
├── text/text.py            # Greeting text templates (mostly unused)
└── media/kit.jpg           # SUP kit photo shown to users
```

---

## How It Works

### Architecture

```
User → Telegram → bot.py (Dispatcher) → Router → Handler → db.py (SQLite)
                                                       ↓
                                            Home Assistant REST API
                                            (smart lock / door sensor)
```

Two async tasks run concurrently:
- **Bot polling** — handles Telegram messages/callbacks
- **APScheduler timer** — fires every 15 seconds, processes all active rentals

### Router Priority (registration order in `bot.py`)
```
rent → finishRent → req → error_report → start (lowest priority / catch-all)
```

### Timer System (`helper/utilits_funk.py`)
Every 15 seconds the `timer()` function iterates all active rentals:

| Tick Math | Meaning |
|---|---|
| 1 tick = 15 seconds | |
| 4 ticks = 1 minute | |
| 20 ticks = 5 minutes | Warning boundary |

| Status | Timer = 0 | Timer > 0 |
|---|---|---|
| Резервація (Reservation) | Cancel, free locker | Decrement |
| Перевірка оплати (Payment check) | Cancel, free locker | Decrement |
| Повторний запит (Re-send) | Cancel, free locker | Decrement |
| Очікування відкриття (Awaiting open) | — | At tick=1: auto-start rental |
| Оренда (Active rental) | — | At tick=20: warn user. At tick=1: notify overage |

### Home Assistant Integration
Uses **Home Assistant REST API** to control lockers:

```
GET  /api/states/{entity_id}          → Read door sensor / lock state
POST /api/services/switch/turn_on     → Unlock locker
POST /api/services/switch/turn_off    → Lock locker
```

For multi-station mode, each station uses its own dedicated Home Assistant endpoint and token (cloudflared HTTPS URL or static/Tailscale IP).
Global HA fallback is not used for station operations.

Each locker in the DB has two HA entity IDs:
- `ha_lock_id` — the switch to open/close
- `ha_door_id` — door sensor that returns `"close"` or `"open"`

After unlock, a 15-second delayed task auto-locks the locker.

---

## FSM Conversation Flows

### Registration (`req.py` — `RegisterFSM`)
```
/start → name → phone (contact share) → consent → confirm → [user saved to DB]
```

### Rental Booking (`rent.py` — `RentBoard`)
```
rent → select station → select locker(s) → select duration 
     → view price + QR payment link → send payment screenshot 
     → [admin review queue]
```
- Pricing is dynamic: weekday vs weekend, equipment type, duration
- Multiple lockers can be selected at once

### Rental Completion (`finishRent.py` — `RentFinishFSM`)
```
finishRent → send equipment photo → close door → bot checks HA door sensor
           → if overtime > 20 ticks (5 min): calculate surcharge, request payment
           → mark complete
```

### Support Ticket (`error_report.py` — `ReportProblem`)
```
error_report → describe problem → attach photo (optional / skip) → confirm → [admin notified]
```

---

## Database Schema (SQLite)

**Key tables:**

| Table | Purpose |
|---|---|
| `users` | `tg_id`, `name`, `phone`, `role`, `create_data` |
| `stations` | `id`, `name`, `location`, `status` |
| `lockers` | `id`, `station_id`, `locker_name`, `status`, `ha_lock_id`, `ha_door_id`, `timer` |
| `inventory_kit` | `locker_id`, `name` (e.g. Стандарт/Максі), `tariff` |
| `tariffs` | `tariff_type`, `day_type` (weekday/weekend), `duration_min`, `price` |
| `rent` | Full rental record — status, timer, payment files, surcharge, total_time |
| `problem` | Support tickets |
| `surcharge` | Overtime payment submissions |

**⚠️ Critical DB schema bug** — two columns referenced in code but missing from the DB:
```sql
-- Run these migrations before using the bot:
ALTER TABLE rent ADD COLUMN complect_file_type TEXT;
ALTER TABLE rent ADD COLUMN complect_file_id TEXT;
ALTER TABLE surcharge ADD COLUMN to_rent TEXT DEFAULT '-';
```
Without these, rental completion and surcharge linking will crash.

---

## How to Deploy

### 1. Prerequisites
- Python 3.10+
- A running Home Assistant instance with a Long-Lived Access Token
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### 2. Install dependencies
```bash
pip install aiogram aiohttp pandas openpyxl environs apscheduler requests
```

### 3. Create `.env` file in project root
```env
BOT_TOKEN=your_telegram_bot_token
ADMINS=123456789,987654321
HA_URL=http://your-homeassistant-ip:8123
HA_TOKEN=your_long_lived_access_token
```

Note:
- `HA_URL` and `HA_TOKEN` can remain for legacy compatibility, but station operations are resolved from `stations` table station-level HA fields.
- For each active station, configure `ha_url_or_ip` and `ha_token` in DB.

### 4. Apply missing DB migrations
```bash
sqlite3 ha_bot.db "ALTER TABLE rent ADD COLUMN complect_file_type TEXT;"
sqlite3 ha_bot.db "ALTER TABLE rent ADD COLUMN complect_file_id TEXT;"
sqlite3 ha_bot.db "ALTER TABLE surcharge ADD COLUMN to_rent TEXT DEFAULT '-';"

# multi-station visibility + station HA config
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;"
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN is_visible_for_clients INTEGER NOT NULL DEFAULT 1;"
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 100;"
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN ha_url_or_ip TEXT;"
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN ha_token TEXT;"
sqlite3 ha_bot.db "ALTER TABLE stations ADD COLUMN auto_lock_delay_sec INTEGER NOT NULL DEFAULT 15;"

# optional indexes
sqlite3 ha_bot.db "CREATE INDEX IF NOT EXISTS idx_stations_visibility ON stations(is_active, is_visible_for_clients, sort_order);"
sqlite3 ha_bot.db "CREATE INDEX IF NOT EXISTS idx_lockers_station_status ON lockers(station_id, status);"
sqlite3 ha_bot.db "CREATE INDEX IF NOT EXISTS idx_rent_station_status ON rent(station_id, status);"
```

### Multi-Station Operations
- Client-visible stations are controlled from DB (`is_visible_for_clients`) and limited to max 10 in runtime logic.
- Admin menu includes station management entry `🏢 Станції` to toggle visibility and activity.
- Station activity depends on station-level HA config. If station HA endpoint/token is missing, locker operations for this station are rejected.

### 5. Run
```bash
python bot.py
```

### Run as background service (Linux)
Create `/etc/systemd/system/ha_bot.service`:
```ini
[Unit]
Description=HA SUP Rental Bot
After=network.target

[Service]
Type=simple
User=andrii
WorkingDirectory=/home/andrii/suppoint-bot
ExecStart=/home/andrii/suppoint-bot/.venv/bin/python /home/andrii/suppoint-bot/bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable ha_bot
sudo systemctl start ha_bot

# service health
sudo systemctl status ha_bot

# follow logs
journalctl -u ha_bot -f

# restart after code updates
sudo systemctl restart ha_bot
```

With this setup, you do not need to run `source .venv/bin/activate` for production service restarts.

---

## How to Test

**There are no automated tests** in the project. Testing is entirely manual:

| What to test | How |
|---|---|
| Bot starts | Run `python bot.py`, send `/start` in Telegram |
| Registration | Click "Реєстрація", complete the flow |
| Rental booking | Click "Орендувати", select station/locker/duration, send a test photo |
| Admin panel | Send `/start` from an admin account (tg_id in `ADMINS`) |
| HA locker control | Use admin menu → Комірки → select locker → Відкрити |
| DB state | Open `ha_bot.db` with `sqlite3` or DB Browser for SQLite |
| Timer | Watch logs — scheduler fires every 15s, prints status |

**Useful debug commands:**
```bash
# Watch live logs
python bot.py 2>&1 | tee bot.log

# Inspect DB
sqlite3 ha_bot.db ".tables"
sqlite3 ha_bot.db "SELECT * FROM rent ORDER BY id DESC LIMIT 10;"
sqlite3 ha_bot.db "SELECT * FROM lockers;"
```

---

## Notable Issues to Fix Before Production

| Severity | Issue |
|---|---|
| **Critical** | Missing DB columns (`complect_file_type`, `complect_file_id`, `to_rent`) |
| **Critical** | Home Assistant URL and token hardcoded in `start.py` and `finishRent.py` — must be moved to `.env` |
| **High** | FSM uses `MemoryStorage` — all user conversation states lost on bot restart |
| **High** | No `requirements.txt` — dependencies must be installed manually |
| **Medium** | `generate_bank_qr_url()` duplicated in `rent.py` and `finishRent.py` |
| **Low** | `ha_bot.db` committed to repo — should be in `.gitignore` |