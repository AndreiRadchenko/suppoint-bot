import sqlite3
import pandas as pd
from datetime import datetime


MAX_VISIBLE_STATIONS = 10

class Database:
    def __init__(self, db_file):
        self.db_path = db_file
        self.ensure_payment_schema()

    def _column_exists(self, cursor, table, column):
        columns = cursor.execute(f"PRAGMA table_info({table})").fetchall()
        return any(col[1] == column for col in columns)

    def _table_exists(self, cursor, table):
        row = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return bool(row)

    def ensure_payment_schema(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS payment_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        payment_type TEXT NOT NULL,
                        tg_id INTEGER NOT NULL,
                        rent_id INTEGER,
                        surcharge_id INTEGER,
                        station_id INTEGER,
                        locker_ids TEXT,
                        amount_minor INTEGER NOT NULL,
                        amount_grn REAL NOT NULL,
                        reference TEXT NOT NULL,
                        external_invoice_id TEXT UNIQUE NOT NULL,
                        checkout_url TEXT,
                        receipt_url TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        raw_payload TEXT,
                        created_at TEXT NOT NULL,
                        paid_at TEXT,
                        updated_at TEXT NOT NULL,
                        invoice_url TEXT
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_reference ON payment_transactions(reference)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_status ON payment_transactions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_invoice ON payment_transactions(external_invoice_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_station_id ON payment_transactions(station_id)")

                if self._table_exists(cursor, 'stations'):
                    if not self._column_exists(cursor, 'stations', 'is_active'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
                    if not self._column_exists(cursor, 'stations', 'is_visible_for_clients'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN is_visible_for_clients INTEGER NOT NULL DEFAULT 1")
                    if not self._column_exists(cursor, 'stations', 'sort_order'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 100")
                    if not self._column_exists(cursor, 'stations', 'ha_url_or_ip'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN ha_url_or_ip TEXT")
                    if not self._column_exists(cursor, 'stations', 'ha_token'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN ha_token TEXT")
                    if not self._column_exists(cursor, 'stations', 'auto_lock_delay_sec'):
                        cursor.execute("ALTER TABLE stations ADD COLUMN auto_lock_delay_sec INTEGER NOT NULL DEFAULT 15")

                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_stations_visibility ON stations(is_active, is_visible_for_clients, sort_order)"
                    )

                if self._table_exists(cursor, 'lockers'):
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lockers_station_status ON lockers(station_id, status)")

                if self._table_exists(cursor, 'rent'):
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rent_station_status ON rent(station_id, status)")

                if self._table_exists(cursor, 'rent'):
                    if not self._column_exists(cursor, 'rent', 'payment_receipt_url'):
                        cursor.execute("ALTER TABLE rent ADD COLUMN payment_receipt_url TEXT")
                    if not self._column_exists(cursor, 'rent', 'payment_invoice_id'):
                        cursor.execute("ALTER TABLE rent ADD COLUMN payment_invoice_id TEXT")

                if self._table_exists(cursor, 'surcharge'):
                    if not self._column_exists(cursor, 'surcharge', 'topup_receipt_url'):
                        cursor.execute("ALTER TABLE surcharge ADD COLUMN topup_receipt_url TEXT")
                    if not self._column_exists(cursor, 'surcharge', 'topup_invoice_id'):
                        cursor.execute("ALTER TABLE surcharge ADD COLUMN topup_invoice_id TEXT")

                if self._table_exists(cursor, 'payment_transactions'):
                    if not self._column_exists(cursor, 'payment_transactions', 'invoice_url'):
                        cursor.execute("ALTER TABLE payment_transactions ADD COLUMN invoice_url TEXT")

                conn.commit()
        except sqlite3.Error as e:
            print("Помилка ensure_payment_schema:", e)

    def user_exists(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
                return bool(result)
        except sqlite3.Error as e:
            print("Помилка у user_exists:", e)

    def add_new_user(self, tg_id, tg_un, name, phone, create_data, role):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (tg_id, tg_un, name, phone, create_data, role) VALUES (?, ?, ?, ?, ?, ?)",
                    (tg_id, tg_un, name, phone, create_data, role)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка у add_new_worker:", e)

    def get_user_by_tg_id(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        except sqlite3.Error as e:
            print("Помилка:", e)

    def add_base_rent(self, tg_id, station_id, select_locker_id, data_create, status, timer):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO rent (tg_id, station_id, select_locker_id, data_create, status, timer) VALUES (?, ?, ?, ?, ?, ?)",
                    (tg_id, station_id, select_locker_id, data_create, status, timer)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка у add_base_rent:", e)

    def update_price_and_time_in_rent(self, tg_id, station_id, locker_id, price, time):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET subscription = ? , base_time = ? WHERE tg_id = ? AND station_id = ? AND select_locker_id =? AND status='Резервація'",
                    (price, time, tg_id, station_id, locker_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def update_status_and_timer_for_rent(self, tg_id, station_id, locker_id, status, timer, file_type, file_id, status_old):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET status = ? , timer = ? , payment_file_type = ?, payment_file_id = ? WHERE tg_id = ? AND station_id = ? AND select_locker_id =? AND status=?",
                    (status, timer, file_type, file_id, tg_id, station_id, locker_id, status_old)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка request_status:", e)

    def update_status_and_timer_for_rent_simple(self, tg_id, station_id, locker_id, status, timer, status_old):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET status = ? , timer = ? WHERE tg_id = ? AND station_id = ? AND select_locker_id = ? AND status = ?",
                    (status, timer, tg_id, station_id, locker_id, status_old)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка update_status_and_timer_for_rent_simple:", e)

    def cancel_rent(self, status, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET status = ?, timer = 0 WHERE id = ?",
                    (status, rent_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка request_status:", e)

    def get_all_actual_rent(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM rent WHERE status = 'Резервація' OR status = 'Очікує оплату' OR status = 'Очікування відкриття' OR status = 'Оренда' OR status = 'Очікує доплату'").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_actual_rent:", e)
            return []

    def get_all_rent(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent ").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_rent:", e)

    def get_all_user(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM users ").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_user:", e)

    def get_rent_dates_by_user(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                SELECT DISTINCT SUBSTR(data_create, 1, 10) as rent_date
                FROM rent
                ORDER BY rent_date DESC
                """
                return [row[0] for row in cursor.execute(query).fetchall()]
        except sqlite3.Error as e:
            print("Помилка в get_rent_dates_by_user:", e)
            return []

    def get_rents_by_date_and_user(self, date_str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                SELECT * FROM rent
                WHERE SUBSTR(data_create, 1, 10) = ?
                ORDER BY data_create
                """
                return cursor.execute(query, (date_str,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rents_by_date_and_user:", e)
            return []

    def get_rents_current_week(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                SELECT * FROM rent
                WHERE strftime('%W', substr(data_create, 7, 4) || '-' || substr(data_create, 4, 2) || '-' || substr(data_create, 1, 2)) = strftime('%W', 'now')
                  AND strftime('%Y', substr(data_create, 7, 4) || '-' || substr(data_create, 4, 2) || '-' || substr(data_create, 1, 2)) = strftime('%Y', 'now')
                ORDER BY data_create
                """
                return cursor.execute(query).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rents_current_week:", e)
            return []

    def get_rents_today(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                SELECT * FROM rent
                WHERE date(substr(data_create, 7, 4) || '-' || substr(data_create, 4, 2) || '-' || substr(data_create, 1, 2))
                      = date('now', 'localtime')
                ORDER BY data_create
                """
                return cursor.execute(query).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rents_today:", e)
            return []

    def get_rents_current_month(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                SELECT * FROM rent
                WHERE strftime('%m', substr(data_create, 7, 4) || '-' || substr(data_create, 4, 2) || '-' || substr(data_create, 1, 2)) = strftime('%m', 'now')
                  AND strftime('%Y', substr(data_create, 7, 4) || '-' || substr(data_create, 4, 2) || '-' || substr(data_create, 1, 2)) = strftime('%Y', 'now')
                ORDER BY data_create
                """
                return cursor.execute(query).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rents_current_month:", e)
            return []

    def get_all_my_rent(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM rent WHERE (status = 'Очікування відкриття' OR status = 'Оренда')  and tg_id = ?",
                    (tg_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def get_all_history(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent WHERE status = 'Завершено' and tg_id = ?",
                                      (tg_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def valid_until_down(self, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET timer = timer - 1 WHERE id = ?",
                    (rent_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка request_status:", e)

    def rent_update_status_and_timer(self, status, timer, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET status = ?, timer = ? WHERE id = ?",
                    (status, timer, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def rent_update_complect_photo(self, complect_file_type, complect_file_id, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET complect_file_type = ?, complect_file_id = ? WHERE id = ?",
                    (complect_file_type, complect_file_id, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def add_total_time(self, total_time, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET total_time = ? WHERE id = ?",
                    (total_time, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def rent_update_pay_1_status(self, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET pay_1 = 'OK' WHERE id = ?",
                    (rent_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_pay_1_status:", e)

    def rent_update_surcharge(self, surcharge, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET surcharge = ?, pay_2 = 'NOT' WHERE id = ?",
                    (surcharge, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_pay_1_status:", e)

    def rent_update_pay_2_status(self, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET pay_2 = 'OK' WHERE id = ?",
                    (rent_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_pay_1_status:", e)

    def get_re_send_rent(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent WHERE tg_id = ? AND status = 'Повторний запит'",
                                      (tg_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rent_by_id:", e)
            return []

    def all_perlimit_rent(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent WHERE tg_id = ? AND status = 'Очікує доплату'",
                                      (tg_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_rent_by_id:", e)
            return []

    def get_lockers_by_station_id(self, station_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM lockers WHERE station_id = ?", (station_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_lockers_by_station_id:", e)
            return []

    def get_all_active_stations(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    """
                    SELECT id, name, location, status
                    FROM stations
                    WHERE status = 'work' AND COALESCE(is_active, 1) = 1
                    ORDER BY COALESCE(sort_order, 100), id
                    """
                ).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def get_visible_stations(self, limit=MAX_VISIBLE_STATIONS):
        try:
            if limit < 1:
                return []
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    """
                    SELECT id, name, location, status, COALESCE(is_active, 1)
                    FROM stations
                    WHERE status = 'work'
                      AND COALESCE(is_visible_for_clients, 1) = 1
                    ORDER BY COALESCE(sort_order, 100), id
                    LIMIT ?
                    """,
                    (min(limit, MAX_VISIBLE_STATIONS),),
                ).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_visible_stations:", e)
            return []

    def get_station_admin_list(self, include_inactive=True):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = (
                    "SELECT id, name, location, status, COALESCE(is_active, 1), "
                    "COALESCE(is_visible_for_clients, 1), COALESCE(sort_order, 100) "
                    "FROM stations"
                )
                params = ()
                if not include_inactive:
                    query += " WHERE COALESCE(is_active, 1) = 1"
                query += " ORDER BY COALESCE(sort_order, 100), id"
                return cursor.execute(query, params).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_station_admin_list:", e)
            return []

    def get_station_by_id(self, station_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    """
                    SELECT id, name, location, status,
                           COALESCE(is_active, 1), COALESCE(is_visible_for_clients, 1),
                           COALESCE(sort_order, 100), ha_url_or_ip, ha_token,
                           COALESCE(auto_lock_delay_sec, 15)
                    FROM stations
                    WHERE id = ?
                    """,
                    (station_id,),
                ).fetchone()
        except sqlite3.Error as e:
            print("Помилка в get_station_by_id:", e)
            return None

    def count_visible_stations(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                row = cursor.execute(
                    "SELECT COUNT(*) FROM stations WHERE COALESCE(is_visible_for_clients, 1) = 1"
                ).fetchone()
                return row[0] if row else 0
        except sqlite3.Error as e:
            print("Помилка в count_visible_stations:", e)
            return 0

    def update_station_visibility(self, station_id, visible):
        try:
            visible_int = 1 if visible else 0
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                current = cursor.execute(
                    "SELECT COALESCE(is_visible_for_clients, 1) FROM stations WHERE id = ?",
                    (station_id,),
                ).fetchone()
                if not current:
                    return False, "Станцію не знайдено"

                already_visible = int(current[0]) == 1
                if visible_int == 1 and not already_visible:
                    visible_count = cursor.execute(
                        "SELECT COUNT(*) FROM stations WHERE COALESCE(is_visible_for_clients, 1) = 1"
                    ).fetchone()[0]
                    if visible_count >= MAX_VISIBLE_STATIONS:
                        return False, f"Максимум {MAX_VISIBLE_STATIONS} видимих станцій"

                cursor.execute(
                    "UPDATE stations SET is_visible_for_clients = ? WHERE id = ?",
                    (visible_int, station_id),
                )
                conn.commit()
                return True, "OK"
        except sqlite3.Error as e:
            print("Помилка в update_station_visibility:", e)
            return False, "Помилка БД"

    def update_station_activity(self, station_id, active):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE stations SET is_active = ? WHERE id = ?",
                    (1 if active else 0, station_id),
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print("Помилка в update_station_activity:", e)
            return False

    def update_station_sort_order(self, station_id, sort_order):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE stations SET sort_order = ? WHERE id = ?",
                    (int(sort_order), station_id),
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print("Помилка в update_station_sort_order:", e)
            return False

    def update_station_ha_config(self, station_id, ha_url_or_ip, ha_token, auto_lock_delay_sec=15):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE stations
                    SET ha_url_or_ip = ?, ha_token = ?, auto_lock_delay_sec = ?
                    WHERE id = ?
                    """,
                    (ha_url_or_ip.strip(), ha_token.strip(), int(auto_lock_delay_sec), station_id),
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print("Помилка в update_station_ha_config:", e)
            return False

    def get_all_available_lockers(self, station_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM lockers WHERE station_id = ? AND status = 'Доступна оренда'",
                    (station_id,)
                ).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_available_lockers:", e)
            return []

    def locker_status(self, status, locker_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE lockers SET status = ? WHERE id = ?",
                    (status, locker_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка locker_status:", e)

    def get_all_reserve_by_tg(self, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM rent WHERE (status = 'Резервація' OR status = 'Очікує оплату') and tg_id = ?",
                    (tg_id,)).fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def get_rent_on_inspection(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent WHERE status = 'Перевірка оплати'").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def get_rent_by_id(self, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM rent WHERE id = ?", (rent_id,)).fetchone()
        except sqlite3.Error as e:
            print("Помилка в get_rent_by_id:", e)

    def get_last_rent_id(self, tg_id, station_id, locker_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT id FROM rent WHERE tg_id = ? AND station_id = ? AND select_locker_id = ? ORDER BY id DESC LIMIT 1",
                    (tg_id, station_id, locker_id)
                ).fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            print("Помилка в get_last_rent_id:", e)
            return None

    def create_payment_transaction(
            self,
            payment_type,
            tg_id,
            rent_id,
            surcharge_id,
            station_id,
            locker_ids,
            amount_minor,
            amount_grn,
            reference,
            external_invoice_id,
            checkout_url,
                status='pending',
                invoice_url=None,
    ):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.utcnow().isoformat()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO payment_transactions (
                        payment_type, tg_id, rent_id, surcharge_id, station_id, locker_ids,
                        amount_minor, amount_grn, reference, external_invoice_id,
                        checkout_url, status, created_at, updated_at, invoice_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payment_type, tg_id, rent_id, surcharge_id, station_id, locker_ids,
                        amount_minor, amount_grn, reference, external_invoice_id,
                        checkout_url, status, now, now, invoice_url
                    )
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка create_payment_transaction:", e)

    def get_payment_transaction_by_invoice_id(self, invoice_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM payment_transactions WHERE external_invoice_id = ?",
                    (invoice_id,)
                ).fetchone()
        except sqlite3.Error as e:
            print("Помилка get_payment_transaction_by_invoice_id:", e)

    def get_pending_payment_transactions(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM payment_transactions WHERE status IN ('pending', 'processing')"
                ).fetchall()
        except sqlite3.Error as e:
            print("Помилка get_pending_payment_transactions:", e)
            return []

    def update_payment_transaction_status(self, invoice_id, status, receipt_url=None, raw_payload=None, invoice_url=None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.utcnow().isoformat()
                paid_at = now if status == 'success' else None
                cursor.execute(
                    """
                    UPDATE payment_transactions
                    SET status = ?, receipt_url = COALESCE(?, receipt_url), raw_payload = ?,
                        paid_at = COALESCE(?, paid_at), updated_at = ?,
                        invoice_url = COALESCE(?, invoice_url)
                    WHERE external_invoice_id = ?
                    """,
                    (status, receipt_url, raw_payload, paid_at, now, invoice_url, invoice_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка update_payment_transaction_status:", e)

    def get_rent_by_tg_station_and_locker_ids(self, tg_id, station_id, locker_ids, status):
        try:
            if not locker_ids:
                return []
            placeholders = ','.join('?' for _ in locker_ids)
            query = (
                f"SELECT * FROM rent WHERE tg_id = ? AND station_id = ? AND status = ? "
                f"AND select_locker_id IN ({placeholders})"
            )
            params = [tg_id, station_id, status, *locker_ids]
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(query, params).fetchall()
        except sqlite3.Error as e:
            print("Помилка get_rent_by_tg_station_and_locker_ids:", e)
            return []

    def save_rent_payment_receipt(self, rent_id, invoice_id, receipt_url):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET payment_invoice_id = ?, payment_receipt_url = ? WHERE id = ?",
                    (invoice_id, receipt_url, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка save_rent_payment_receipt:", e)

    def save_surcharge_payment_receipt(self, surcharge_id, invoice_id, receipt_url):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE surcharge SET topup_invoice_id = ?, topup_receipt_url = ? WHERE id = ?",
                    (invoice_id, receipt_url, surcharge_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка save_surcharge_payment_receipt:", e)

    def get_or_create_surcharge_for_rent(self, rent_id, tg_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                row = cursor.execute("SELECT * FROM surcharge WHERE to_rent = ?", (str(rent_id),)).fetchone()
                if row:
                    return row[0]

                create_date = datetime.now().strftime("%d.%m.%Y %H:%M")
                cursor.execute(
                    "INSERT INTO surcharge (tg_id, file_type, file_id, date_create, status, to_rent) VALUES (?, ?, ?, ?, ?, ?)",
                    (tg_id, 'none', 'none', create_date, 'Очікує оплату', str(rent_id))
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            print("Помилка get_or_create_surcharge_for_rent:", e)
            return None

    def rent_update_status(self, status, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE rent SET status = ? WHERE id = ?",
                    (status, rent_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def get_locker_by_locker_id(self, locker_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM lockers WHERE id = ?", (locker_id,)).fetchone()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def get_inventory_kit_by_locker_and_station_id(self, station_id, locker_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM inventory_kit WHERE in_station = ? AND in_locker = ?",
                    (station_id, locker_id)
                ).fetchone()
        except sqlite3.Error as e:
            print("Помилка в get_inventory_kit_by_locker_and_station_id:", e)
            return []

    def get_tariff_by_data(self, tariff_type, day_type, time):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute(
                    "SELECT * FROM tariffs WHERE tariff_type = ? AND day_type = ? AND duration_min = ?",
                    (tariff_type, day_type, time)
                ).fetchone()
        except sqlite3.Error as e:
            print("Помилка в get_tariff_by_data:", e)
            return []

    def locker_update_status_and_timer(self, status, timer, locker_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE lockers SET status = ?, timer = ? WHERE id = ?",
                    (status, timer, locker_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка request_status:", e)

    def create_problem_report(self, tg_id, user_name, user_phone, current_rent, dock_type, dock_id, text, status,
                              date_create):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO problem (tg_id, user_name, user_phone, current_rent, dock_type, dock_id, text, status, date_create) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tg_id, user_name, user_phone, current_rent, dock_type, dock_id, text, status, date_create)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка у create_problem_report:", e)

    def get_open_problem(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM problem WHERE status = 'Новий'").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def problem_update_status(self, status, problem_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE problem SET status = ? WHERE id = ?",
                    (status, problem_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка rent_update_status:", e)

    def add_new_surcharge(self, tg_id, file_type, file_id, date_create):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO surcharge (tg_id, file_type, file_id, date_create) VALUES (?, ?, ?, ?)",
                    (tg_id, file_type, file_id, date_create)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка у create_problem_report:", e)

    def get_new_surcharge(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                return cursor.execute("SELECT * FROM surcharge WHERE status = 'Новий'").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def surcharge_update_status(self, status, surcharge_id, to_rent='-'):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE surcharge SET status = ?, to_rent = ? WHERE id = ?",
                    (status, to_rent, surcharge_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print("Помилка surcharge_update_status:", e)

    def get_surcharge_by_rent(self, rent_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute("SELECT * FROM surcharge WHERE to_rent = ?", (rent_id,)).fetchone()
            return result
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

    def export_all_rent_to_excel(self, excel_path):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                data = cursor.execute("SELECT * FROM rent").fetchall()
                columns = [desc[0] for desc in cursor.description]

            # Формуємо DataFrame і зберігаємо в Excel
            pd.DataFrame(data, columns=columns).to_excel(excel_path, index=False, engine='openpyxl')

            print(f"✅ Дані з rent збережено у {excel_path}")
        except sqlite3.Error as e:
            print("Помилка в export_all_rent_to_excel:", e)