# ha_bot

'available', 'rented', 'reserved', 'maintenance'
«доступний», «орендований», «зарезервований», «обслуговування»

'available' - доступний
'in_process' - користувач оформлюж
'on_inspection' - оічкує перевірку


rental_started - оренду розпочато

## Project Analysis: `ha_bot` — SUP Board Rental Telegram Bot

---

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

**Dependencies to install** (no `requirements.txt` exists):
```bash
pip install aiogram aiohttp pandas openpyxl environs apscheduler requests
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

### 4. Apply missing DB migrations
```bash
sqlite3 ha_bot.db "ALTER TABLE rent ADD COLUMN complect_file_type TEXT;"
sqlite3 ha_bot.db "ALTER TABLE rent ADD COLUMN complect_file_id TEXT;"
sqlite3 ha_bot.db "ALTER TABLE surcharge ADD COLUMN to_rent TEXT DEFAULT '-';"
```

### 5. Run
```bash
python bot.py
```

### Run as background service (Linux)
Create `/etc/systemd/system/ha_bot.service`:
```ini
[Unit]
Description=HA SUP Rental Bot

[Service]
WorkingDirectory=/path/to/ha_bot-main
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
systemctl enable ha_bot && systemctl start ha_bot
```

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