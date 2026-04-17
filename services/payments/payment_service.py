import json
import hashlib
import logging
from base64 import b64decode
from datetime import datetime, timedelta
from typing import Optional

from ecdsa import BadSignatureError, VerifyingKey
from ecdsa.util import sigdecode_der

from config_data.config import Config, load_config
from create_bot import bot
from db import Database
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
        self._pubkey_value: Optional[str] = None
        self._pubkey_expires_at: Optional[datetime] = None

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
    ) -> str:
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

        return result["pageUrl"]

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

    async def create_topup_invoice(self, rent_id: int, tg_id: int, amount_grn: float, destination: str) -> str:
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

        return result["pageUrl"]

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

        if payment_type == "initial":
            locker_ids = [int(item) for item in locker_ids_raw.split(",") if item]
            rents = self.db.get_rent_by_tg_station_and_locker_ids(tg_id, station_id, locker_ids, "Очікує оплату")
            for rent in rents:
                self.db.rent_update_status_and_timer("Очікування відкриття", 20, rent[0])
                self.db.locker_status("Очікування відкриття", rent[3])
                self.db.rent_update_pay_1_status(rent[0])
                self.db.save_rent_payment_receipt(rent[0], invoice_id, receipt_url)

            await bot.send_message(
                tg_id,
                "✅ Оплату підтверджено автоматично.\n\n"
                "🚪 Доступ до комірки відкрито.\n"
                "Перейдіть у розділ 🛶 Мої оренди та натисніть 🔓 Відкрити комірку.",
            )
            return

        if payment_type == "topup" and rent_id:
            self.db.rent_update_pay_2_status(rent_id)
            self.db.rent_update_status_and_timer("Завершено", 0, rent_id)
            if surcharge_id:
                self.db.surcharge_update_status("Враховано", surcharge_id, str(rent_id))
                self.db.save_surcharge_payment_receipt(surcharge_id, invoice_id, receipt_url)

            await bot.send_message(
                tg_id,
                "✅ Доплату підтверджено автоматично. Дякуємо, оренду завершено.",
            )

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
