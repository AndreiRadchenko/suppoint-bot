import json
import hashlib
import logging
import asyncio
from contextlib import suppress
from base64 import b64decode
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from ecdsa import BadSignatureError, VerifyingKey
from ecdsa.util import sigdecode_der

from config_data.config import Config, load_config
from create_bot import bot
from db import Database
from kb import kb
from .checkbox_client import CheckboxClient, FiscalResult
from .monobank_client import MonobankClient


STATUS_MAP = {
    "created": "pending",
    "processing": "processing",
    "hold": "processing",
    "success": "success",
    "failure": "failed",
    "reversed": "failed",
    "expired": "expired",
}


class PaymentService:
    def __init__(self):
        self.config: Config = load_config()
        self.db = Database(self.config.db.path)
        self.client = MonobankClient(self._resolve_token())
        self.checkbox_client = CheckboxClient(self.config)
        self._pubkey_value: Optional[str] = None
        self._pubkey_expires_at: Optional[datetime] = None
        self._last_shift_close_date: Optional[str] = None

    def _resolve_token(self) -> str:
        if self.config.payment.mono_mode == "live":
            return self.config.payment.mono_live_token
        return self.config.payment.mono_test_token

    async def _get_cached_pubkey(self, force_refresh: bool = False) -> str:
        now = datetime.utcnow()
        if (
            not force_refresh
            and self._pubkey_value
            and self._pubkey_expires_at
            and self._pubkey_expires_at > now
        ):
            return self._pubkey_value

        pubkey = await self.client.get_public_key()
        self._pubkey_value = pubkey
        self._pubkey_expires_at = now + timedelta(seconds=self.config.payment.mono_pubkey_cache_ttl)
        return pubkey

    def _verify_with_pubkey(self, raw_body: bytes, x_sign_b64: str, pubkey_b64: str) -> bool:
        pem = b64decode(pubkey_b64)
        vk = VerifyingKey.from_pem(pem)
        signature = b64decode(x_sign_b64)
        body_hash = hashlib.sha256(raw_body).digest()
        try:
            vk.verify_digest(signature, body_hash, sigdecode=sigdecode_der)
            return True
        except BadSignatureError:
            return False

    async def verify_webhook_signature(self, raw_body: bytes, x_sign_b64: str) -> bool:
        pubkey = await self._get_cached_pubkey(force_refresh=False)
        if self._verify_with_pubkey(raw_body, x_sign_b64, pubkey):
            return True

        pubkey = await self._get_cached_pubkey(force_refresh=True)
        return self._verify_with_pubkey(raw_body, x_sign_b64, pubkey)

    async def create_initial_invoice(
        self,
        tg_id: int,
        station_id: int,
        locker_ids: list[int],
        amount_grn: float,
        destination: str,
    ) -> tuple[str, str]:
        self._validate_station_lockers(station_id, locker_ids)
        amount_minor = int(amount_grn * 100)
        reference = f"rent-{tg_id}-{int(datetime.utcnow().timestamp())}"
        webhook_url = self._webhook_public_url()
        payload = {
            "amount": amount_minor,
            "merchantPaymInfo": {
                "reference": reference,
                "destination": destination,
            },
            "redirectUrl": self.config.payment.mono_redirect_url,
        }
        if webhook_url:
            payload["webHookUrl"] = webhook_url

        result = await self.client.create_invoice(payload)

        primary_rent_id = None
        for locker_id in locker_ids:
            rent_id = self.db.get_last_rent_id(tg_id, station_id, locker_id)
            if rent_id:
                primary_rent_id = primary_rent_id or rent_id

        self.db.create_payment_transaction(
            payment_type="initial",
            tg_id=tg_id,
            rent_id=primary_rent_id,
            surcharge_id=None,
            station_id=station_id,
            locker_ids=",".join(str(locker_id) for locker_id in locker_ids),
            amount_minor=amount_minor,
            amount_grn=float(amount_grn),
            reference=reference,
            external_invoice_id=result["invoiceId"],
            checkout_url=result["pageUrl"],
            status="pending",
            invoice_url=result.get("pageUrl"),
        )

        return result["pageUrl"], result["invoiceId"]

    def _validate_station_lockers(self, station_id: int, locker_ids: list[int]) -> None:
        if not locker_ids:
            raise ValueError("locker_ids must not be empty")

        normalized = [int(locker_id) for locker_id in locker_ids]
        if len(set(normalized)) != len(normalized):
            raise ValueError("locker_ids must be unique")

        station = self.db.get_station_by_id(station_id)
        if not station:
            raise ValueError(f"station_id {station_id} not found")

        for locker_id in normalized:
            locker = self.db.get_locker_by_locker_id(locker_id)
            if not locker:
                raise ValueError(f"locker_id {locker_id} not found")
            if int(locker[1]) != int(station_id):
                raise ValueError(
                    f"locker_id {locker_id} belongs to station {locker[1]}, expected {station_id}"
                )

    async def create_topup_invoice(self, rent_id: int, tg_id: int, amount_grn: float, destination: str) -> tuple[str, str]:
        amount_minor = int(amount_grn * 100)
        reference = f"topup-{rent_id}-{int(datetime.utcnow().timestamp())}"
        webhook_url = self._webhook_public_url()
        payload = {
            "amount": amount_minor,
            "merchantPaymInfo": {
                "reference": reference,
                "destination": destination,
            },
            "redirectUrl": self.config.payment.mono_redirect_url,
        }
        if webhook_url:
            payload["webHookUrl"] = webhook_url
        result = await self.client.create_invoice(payload)

        surcharge_id = self.db.get_or_create_surcharge_for_rent(rent_id, tg_id)

        self.db.create_payment_transaction(
            payment_type="topup",
            tg_id=tg_id,
            rent_id=rent_id,
            surcharge_id=surcharge_id,
            station_id=None,
            locker_ids=None,
            amount_minor=amount_minor,
            amount_grn=float(amount_grn),
            reference=reference,
            external_invoice_id=result["invoiceId"],
            checkout_url=result["pageUrl"],
            status="pending",
            invoice_url=result.get("pageUrl"),
        )

        return result["pageUrl"], result["invoiceId"]

    def _webhook_public_url(self) -> Optional[str]:
        public_base = (self.config.payment.mono_webhook_public_base or '').strip().rstrip('/')
        path = self.config.payment.mono_webhook_path
        if public_base:
            if public_base.startswith("https://"):
                return f"{public_base}{path}"
            logging.warning(
                "MONO_WEBHOOK_PUBLIC_BASE must start with https://, skipping webHookUrl: %s",
                public_base,
            )
            return None

        host = self.config.payment.mono_webhook_host
        if host in {"0.0.0.0", "127.0.0.1", "localhost"}:
            # Monobank rejects localhost/private callback URLs.
            return None
        return f"https://{host}{path}"

    async def process_webhook_payload(self, payload: dict, raw_body: bytes):
        invoice_id = payload.get("invoiceId")
        if not invoice_id:
            return

        tx = self.db.get_payment_transaction_by_invoice_id(invoice_id)
        if not tx:
            return

        mono_status = payload.get("status", "created")
        normalized_status = STATUS_MAP.get(mono_status, "pending")
        existing_status = tx[13]

        # Idempotency: if already finalized, ignore duplicates.
        if existing_status in {"success", "failed", "expired"}:
            return

        invoice_url = payload.get("invoiceUrl") or (tx[18] if len(tx) > 18 else tx[11])
        receipt_url = payload.get("receiptUrl") or tx[12]

        if normalized_status == "success" and (not receipt_url or not invoice_url):
            status_invoice_url, status_receipt_url = await self._enrich_urls_from_status(invoice_id)
            invoice_url = status_invoice_url or invoice_url
            receipt_url = status_receipt_url or receipt_url

        self.db.update_payment_transaction_status(
            invoice_id=invoice_id,
            status=normalized_status,
            receipt_url=receipt_url,
            raw_payload=raw_body.decode("utf-8", errors="ignore"),
            invoice_url=invoice_url,
        )

        if normalized_status == "success":
            if not receipt_url:
                logging.info(
                    "Monobank success without receipt URL for invoice %s; saved invoice_url only",
                    invoice_id,
                )
            await self._mark_paid(tx, invoice_id, receipt_url)
            return

        if normalized_status in {"failed", "expired"}:
            await bot.send_message(
                tx[2],
                "Оплата не завершена. Спробуйте оплатити ще раз у меню оренди.",
            )

    async def _mark_paid(self, tx, invoice_id: str, receipt_url: Optional[str]):
        payment_type = tx[1]
        tg_id = tx[2]
        rent_id = tx[3]
        surcharge_id = tx[4]
        station_id = tx[5]
        locker_ids_raw = tx[6] or ""
        link_message_id = tx[24] if len(tx) > 24 else None

        if link_message_id:
            with suppress(Exception):
                await bot.delete_message(tg_id, link_message_id)

        if payment_type == "initial":
            locker_ids = [int(item) for item in locker_ids_raw.split(",") if item]
            rents = self.db.get_rent_by_tg_station_and_locker_ids(tg_id, station_id, locker_ids, "Очікує оплату")
            for rent in rents:
                self.db.rent_update_status_and_timer("Очікування відкриття", 20, rent[0])
                self.db.locker_status("Очікування відкриття", rent[3])
                self.db.rent_update_pay_1_status(rent[0])
                self.db.save_rent_payment_receipt(rent[0], invoice_id, receipt_url)

            await self._start_fiscalization(tx, invoice_id)
            await bot.send_message(
                tg_id,
                "✅ Оплату підтверджено автоматично.\n\n"
                "🚪 Доступ до комірки відкрито.\n"
                "Перейдіть у розділ 🛶 Мої оренди та натисніть 🔓 Відкрити комірку.",
                reply_markup=kb.user_menu,
            )
            # asyncio.create_task(self._start_fiscalization(tx, invoice_id))
            # return

        if payment_type == "topup" and rent_id:
            self.db.rent_update_pay_2_status(rent_id)
            self.db.rent_update_status_and_timer("Завершено", 0, rent_id)
            if surcharge_id:
                self.db.surcharge_update_status("Враховано", surcharge_id, str(rent_id))
                self.db.save_surcharge_payment_receipt(surcharge_id, invoice_id, receipt_url)

            await self._start_fiscalization(tx, invoice_id)
            await bot.send_message(
                tg_id,
                "✅ Доплату підтверджено автоматично. Дякуємо, оренду завершено.",
                reply_markup=kb.user_menu,
            )
            # asyncio.create_task(self._start_fiscalization(tx, invoice_id))

    def _resolve_station_location_for_tx(self, tx) -> str:
        station_id = tx[5]
        if not station_id and tx[3]:
            rent = self.db.get_rent_by_id(tx[3])
            if rent:
                station_id = rent[2]

        if not station_id:
            return "Невідома локація"

        station = self.db.get_station_by_id(station_id)
        if not station:
            return f"Станція #{station_id}"
        return station[2] or f"Станція #{station_id}"

    def _resolve_station_info_for_tx(self, tx) -> tuple[str, str]:
        """Returns (name, location) for the station linked to tx."""
        station_id = tx[5]
        if not station_id and tx[3]:
            rent = self.db.get_rent_by_id(tx[3])
            if rent:
                station_id = rent[2]

        if not station_id:
            return ("Невідома станція", "")

        station = self.db.get_station_by_id(station_id)
        if not station:
            return (f"Станція #{station_id}", "")
        return (station[1] or f"Станція #{station_id}", station[2] or "")

    def _build_checkbox_sale_payload(self, tx, invoice_id: str) -> dict:
        payment_type = tx[1]
        amount_minor = int(tx[7] or 0)
        reference = tx[9] or invoice_id

        station_name, station_location = self._resolve_station_info_for_tx(tx)
        station_label = f"{station_name} ({station_location})" if station_location else station_name

        rent = self.db.get_rent_by_id(tx[3]) if tx[3] else None

        if payment_type == "topup":
            duration_str = ""
            if rent:
                try:
                    base_time = int(rent[4]) if rent[4] is not None else 0
                    total_time = int(rent[14]) if rent[14] is not None else 0
                    overtime = total_time - base_time
                    if overtime > 0:
                        duration_str = f". Додатковий час {overtime} хв"
                except (TypeError, ValueError):
                    pass
            item_name = f"Доплата за оренду спорядження. Станція: {station_label}{duration_str}"
            item_code = "SUP_TOPUP"
        else:
            duration_str = ""
            if rent:
                try:
                    base_time = int(rent[4])
                    if base_time > 0:
                        duration_str = f". Тривалість {base_time} хв"
                except (TypeError, ValueError):
                    pass
            item_name = f"Оренда спорядження. Станція: {station_label}{duration_str}"
            item_code = "SUP_RENTAL"

        # Determine quantity from locker_ids for initial payments.
        locker_count = 1
        if payment_type == "initial":
            locker_ids_raw = tx[6] or ""
            ids = [x for x in locker_ids_raw.split(",") if x]
            if len(ids) > 1:
                locker_count = len(ids)

        # Use n × unit_price only when it divides evenly — Checkbox requires
        # goods total (price * quantity / 1000) to exactly match payments.value.
        if locker_count > 1 and amount_minor % locker_count == 0:
            unit_price = amount_minor // locker_count
            goods_quantity = locker_count * 1000
        else:
            unit_price = amount_minor
            goods_quantity = 1000

        return {
            # Checkbox ReceiptSellPayload requires goods[].good object.
            "id": str(uuid4()),
            "goods": [
                {
                    "good": {
                        "code": item_code,
                        "name": item_name,
                        "price": unit_price,
                    },
                    # 1000 = 1 unit in Checkbox quantity scale.
                    "quantity": goods_quantity,
                }
            ],
            "payments": [
                {
                    "type": "CASHLESS",
                    "value": amount_minor,
                    "label": "Інтернет еквайринг",
                }
            ],
            "context": {
                "invoice_id": invoice_id,
                "reference": reference,
            },
        }

    async def _send_receipt_email_if_configured(self, invoice_id: str) -> None:
        email = (self.config.payment.mono_receipt_email_fallback or "").strip()
        if not email:
            return

        try:
            await self.client.send_receipt_email(invoice_id, email)
        except Exception as error:
            logging.warning("Failed to send receipt email for %s: %s", invoice_id, error)

    async def _notify_fiscal_receipt(self, tx, invoice_id: str, fiscal_result: FiscalResult) -> None:
        tg_id = tx[2]
        receipt_url = fiscal_result.receipt_url

        if receipt_url:
            await bot.send_message(
                tg_id,
                f'<a href="{receipt_url}">🧾 Чек про оплату</a>',
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                tg_id,
                "🧾 Оплату фіскалізовано, але посилання на чек поки недоступне.",
            )

        if fiscal_result.pdf_url:
            with suppress(Exception):
                await bot.send_document(
                    tg_id,
                    fiscal_result.pdf_url,
                    caption="PDF чека",
                )

        await self._send_receipt_email_if_configured(invoice_id)

    async def _start_fiscalization(self, tx, invoice_id: str) -> None:
        if not self.checkbox_client.enabled:
            logging.info("Checkbox fiscalization is disabled, skip invoice %s", invoice_id)
            return

        if len(tx) > 19 and tx[19] in {"success", "failed"}:
            return

        self.db.update_payment_transaction_fiscal(
            invoice_id=invoice_id,
            fiscal_status="pending",
            fiscal_provider="checkbox",
            fiscal_error=None,
        )

        payload = self._build_checkbox_sale_payload(tx, invoice_id)
        result = await self.checkbox_client.create_sale_receipt(payload)

        if result.status == "success":
            self.db.update_payment_transaction_fiscal(
                invoice_id=invoice_id,
                fiscal_status="success",
                receipt_url=result.receipt_url,
                fiscal_external_id=result.receipt_id,
                fiscal_provider="checkbox",
                fiscal_error=None,
            )
            # await self._notify_fiscal_receipt(tx, invoice_id, result)
            return

        if result.status == "failed":
            if self._is_retryable_fiscal_error(result):
                self.db.update_payment_transaction_fiscal(
                    invoice_id=invoice_id,
                    fiscal_status="processing",
                    fiscal_external_id=result.receipt_id,
                    fiscal_provider="checkbox",
                    fiscal_error=result.error_text,
                )
                logging.warning(
                    "Checkbox retryable fiscal error for %s: %s",
                    invoice_id,
                    result.error_text,
                )
                return

            self.db.update_payment_transaction_fiscal(
                invoice_id=invoice_id,
                fiscal_status="failed",
                fiscal_external_id=result.receipt_id,
                fiscal_provider="checkbox",
                fiscal_error=result.error_text,
            )
            return

        self.db.update_payment_transaction_fiscal(
            invoice_id=invoice_id,
            fiscal_status="processing",
            fiscal_external_id=result.receipt_id,
            fiscal_provider="checkbox",
            fiscal_error=result.error_text,
            # Save receipt_url now so reconcile loop knows notification was already sent.
            receipt_url=result.receipt_url if (result.receipt_id and result.receipt_url) else None,
        )
        # Receipt ID is assigned immediately even when status is still "CREATED".
        # Notify the user right away — the public URL is valid from the moment the ID exists.
        if result.receipt_id and result.receipt_url:
            await self._notify_fiscal_receipt(tx, invoice_id, result)

    def _is_fiscal_retry_expired(self, tx) -> bool:
        window_min = max(1, int(self.config.payment.fiscal_retry_window_min))
        base_value = tx[16] or tx[15]
        if not base_value:
            return False

        try:
            base_dt = datetime.fromisoformat(base_value)
        except Exception:
            return False

        return datetime.utcnow() > base_dt + timedelta(minutes=window_min)

    def _is_retryable_fiscal_error(self, result: FiscalResult) -> bool:
        code = (result.error_code or "").strip().lower()
        text = (result.error_text or "").strip().lower()

        # Checkbox cannot fiscalize when cashier shift is closed.
        if code == "shift.not_opened":
            return True
        if "shift.not_opened" in text or "зміну не відкрито" in text:
            return True

        return False

    async def reconcile_fiscal_transactions(self):
        if not self.checkbox_client.enabled:
            return

        pending = self.db.get_pending_fiscal_transactions()
        for tx in pending:
            invoice_id = tx[10]
            fiscal_status = tx[19] if len(tx) > 19 and tx[19] else "not_started"
            fiscal_external_id = tx[20] if len(tx) > 20 else None

            if self._is_fiscal_retry_expired(tx):
                self.db.update_payment_transaction_fiscal(
                    invoice_id=invoice_id,
                    fiscal_status="failed",
                    fiscal_provider="checkbox",
                    fiscal_error="Fiscal retry window expired",
                )
                continue

            if fiscal_status == "not_started":
                await self._start_fiscalization(tx, invoice_id)
                continue

            if fiscal_status in {"pending", "processing"} and not fiscal_external_id:
                await self._start_fiscalization(tx, invoice_id)
                continue

            if fiscal_status in {"pending", "processing"} and fiscal_external_id:
                result = await self.checkbox_client.get_receipt_status(str(fiscal_external_id))
                if result.status == "success":
                    self.db.update_payment_transaction_fiscal(
                        invoice_id=invoice_id,
                        fiscal_status="success",
                        receipt_url=result.receipt_url,
                        fiscal_external_id=result.receipt_id or str(fiscal_external_id),
                        fiscal_provider="checkbox",
                        fiscal_error=None,
                    )
                    # tx[12] is receipt_url — if already set, _start_fiscalization already notified.
                    if not tx[12]:
                        await self._notify_fiscal_receipt(tx, invoice_id, result)
                elif result.status == "failed":
                    if self._is_retryable_fiscal_error(result):
                        self.db.update_payment_transaction_fiscal(
                            invoice_id=invoice_id,
                            fiscal_status="processing",
                            fiscal_external_id=result.receipt_id or str(fiscal_external_id),
                            fiscal_provider="checkbox",
                            fiscal_error=result.error_text,
                        )
                        continue

                    self.db.update_payment_transaction_fiscal(
                        invoice_id=invoice_id,
                        fiscal_status="failed",
                        fiscal_external_id=result.receipt_id or str(fiscal_external_id),
                        fiscal_provider="checkbox",
                        fiscal_error=result.error_text,
                    )
                else:
                    self.db.update_payment_transaction_fiscal(
                        invoice_id=invoice_id,
                        fiscal_status="processing",
                        fiscal_external_id=result.receipt_id or str(fiscal_external_id),
                        fiscal_provider="checkbox",
                        fiscal_error=result.error_text,
                    )

    async def enforce_checkbox_shift_policy(self) -> None:
        if not self.checkbox_client.enabled:
            return

        try:
            tz_name = self.config.payment.checkbox_shift_timezone or "Europe/Kyiv"
            now_local = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now_local = datetime.utcnow()

        now_hhmm = now_local.strftime("%H:%M")
        today_key = now_local.strftime("%Y-%m-%d")

        # Checkbox shift must be closed during the same day; auto-close by 23:45.
        if now_hhmm >= "23:45" and self._last_shift_close_date != today_key:
            closed = await self.checkbox_client.close_shift()
            if closed:
                self._last_shift_close_date = today_key
                logging.info("Checkbox daily shift auto-close completed for %s", today_key)

    async def _enrich_urls_from_status(self, invoice_id: str) -> tuple[Optional[str], Optional[str]]:
        try:
            status_payload = await self.client.get_invoice_status(invoice_id)
        except Exception as error:
            logging.warning("Failed to enrich invoice %s URLs from status: %s", invoice_id, error)
            return None, None

        invoice_url = status_payload.get("invoiceUrl")
        receipt_url = status_payload.get("receiptUrl")
        return invoice_url, receipt_url

    async def reconcile_pending_transactions(self):
        pending = self.db.get_pending_payment_transactions()
        for tx in pending:
            invoice_id = tx[10]
            try:
                payload = await self.client.get_invoice_status(invoice_id)
                await self.process_webhook_payload(payload, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            except Exception as error:
                error_text = str(error)
                # Old or foreign-environment invoices may return errCode 1004 (invoice not found).
                # Mark as terminal to avoid infinite reconcile retries and log noise.
                if "'errCode': '1004'" in error_text or '"errCode": "1004"' in error_text or "invoice not found" in error_text:
                    self.db.update_payment_transaction_status(
                        invoice_id=invoice_id,
                        status="failed",
                        raw_payload=error_text,
                    )
                    logging.info(
                        "Marked invoice %s as failed after reconcile not-found response (errCode 1004)",
                        invoice_id,
                    )
                    continue

                print(f"Помилка reconcile_pending_transactions для {invoice_id}: {error}")
