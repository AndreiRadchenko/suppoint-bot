import sqlite3
import pandas as pd

class Database:
    def __init__(self, db_file):
        self.db_path = db_file

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
                return cursor.execute("SELECT * FROM stations WHERE status = 'work'").fetchall()
        except sqlite3.Error as e:
            print("Помилка в get_all_active_stations:", e)

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
                    "SELECT * FROM rent WHERE status = 'Резервація' and tg_id = ?",
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