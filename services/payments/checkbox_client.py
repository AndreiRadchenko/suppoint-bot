import aiohttp
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from config_data.config import Config


@dataclass
class FiscalResult:
    status: str
    receipt_id: Optional[str] = None
    receipt_url: Optional[str] = None
    pdf_url: Optional[str] = None
    error_code: Optional[str] = None
    error_text: Optional[str] = None
    raw_payload: Optional[dict] = None


class CheckboxClient:
    def __init__(self, config: Config):
        self.config = config

    def _resolve_token(self) -> str:
        mode = (self.config.payment.checkbox_mode or "test").strip().lower()
        if mode == "live":
            return (self.config.payment.checkbox_live_token or self.config.payment.checkbox_api_token or "").strip()
        return (self.config.payment.checkbox_test_token or self.config.payment.checkbox_api_token or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.config.payment.checkbox_enabled and self._resolve_token())

    def _headers(self, include_license_key: bool = False):
        headers = {
            "Authorization": f"Bearer {self._resolve_token()}",
            "Content-Type": "application/json",
        }
        if include_license_key:
            license_key = (self.config.payment.checkbox_license_key or "").strip()
            if license_key:
                headers["X-License-Key"] = license_key
        return headers

    def _is_shift_not_opened(self, payload: Optional[dict], error_code: Optional[str], error_text: Optional[str]) -> bool:
        code = (error_code or '').strip().lower()
        text = (error_text or '').strip().lower()
        if code == 'shift.not_opened':
            return True
        if 'shift.not_opened' in text or 'зміну не відкрито' in text:
            return True
        if isinstance(payload, dict):
            payload_code = str(payload.get('code') or '').strip().lower()
            if payload_code == 'shift.not_opened':
                return True
        return False

    def _is_offline_required_error(self, payload: Optional[dict], error_code: Optional[str], error_text: Optional[str]) -> bool:
        code = (error_code or '').strip().lower()
        text = (error_text or '').strip().lower()
        if code == 'cash_register.should_be_offline':
            return True
        if 'should_be_offline' in text or 'manual offline mode' in text:
            return True
        if isinstance(payload, dict):
            payload_code = str(payload.get('code') or '').strip().lower()
            if payload_code == 'cash_register.should_be_offline':
                return True
        return False

    def _open_shift_payload(self) -> dict:
        raw = (self.config.payment.checkbox_open_shift_payload or '{}').strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                # CreateShiftPayload allowed fields.
                allowed = {"id", "auto_close_at", "fiscal_code", "fiscal_date"}
                payload = {k: v for k, v in parsed.items() if k in allowed and v is not None}

                if "auto_close_at" not in payload:
                    payload["auto_close_at"] = self._default_auto_close_at_iso()

                if "id" not in payload:
                    payload["id"] = str(uuid4())

                if "fiscal_code" not in payload:
                    payload["fiscal_code"] = self._default_fiscal_code()

                if "fiscal_date" not in payload:
                    payload["fiscal_date"] = self._utc_now_iso()

                return payload
        except Exception:
            pass
        return {
            "id": str(uuid4()),
            "auto_close_at": self._default_auto_close_at_iso(),
            "fiscal_code": self._default_fiscal_code(),
            "fiscal_date": self._utc_now_iso(),
        }

    def _close_shift_payload(self) -> dict:
        raw = (self.config.payment.checkbox_close_shift_payload or '{}').strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                # CloseShiftPayload allowed fields.
                allowed = {"skip_client_name_check", "report", "fiscal_code", "fiscal_date"}
                return {k: v for k, v in parsed.items() if k in allowed and v is not None}
        except Exception:
            pass
        return {}

    def _go_offline_payload(self) -> dict:
        raw = (self.config.payment.checkbox_go_offline_payload or '{}').strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                allowed = {"go_offline_date", "fiscal_code"}
                return {k: v for k, v in parsed.items() if k in allowed and v is not None}
        except Exception:
            pass

        return {
            "go_offline_date": self._utc_now_iso(),
            "fiscal_code": self._default_fiscal_code(),
        }

    def _default_auto_close_at_iso(self) -> str:
        tz_name = self.config.payment.checkbox_shift_timezone or "Europe/Kyiv"
        close_time = (self.config.payment.checkbox_shift_auto_close_time or "23:45").strip()

        hour = 23
        minute = 45
        try:
            hh, mm = close_time.split(":", 1)
            hour = max(0, min(23, int(hh)))
            minute = max(0, min(59, int(mm)))
        except Exception:
            pass

        try:
            now_local = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now_local = datetime.now()

        dt = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

    def _utc_now_iso(self) -> str:
        return datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

    def _default_fiscal_code(self) -> str:
        prefix = (self.config.payment.checkbox_shift_fiscal_code_prefix or "AUTO").strip() or "AUTO"
        return f"{prefix}-{uuid4().hex[:12]}"

    async def open_shift(self) -> bool:
        if not self.enabled:
            return False

        if not (self.config.payment.checkbox_license_key or "").strip():
            logging.warning("Checkbox open shift skipped: CHECKBOX_LICENSE_KEY is empty")
            return False

        timeout = self.config.payment.checkbox_request_timeout_sec
        url = (
            f"{self.config.payment.checkbox_api_base_url.rstrip('/')}"
            f"{self.config.payment.checkbox_open_shift_endpoint}"
        )
        payload = self._open_shift_payload()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(url, headers=self._headers(include_license_key=True), json=payload) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        if self._is_offline_required_error(
                            data,
                            data.get("code") if isinstance(data, dict) else None,
                            str(data),
                        ):
                            logging.warning("Checkbox open shift requires offline mode, trying go-offline")
                            switched = await self.go_offline()
                            if switched:
                                retry_payload = self._open_shift_payload()
                                async with session.post(
                                    url,
                                    headers=self._headers(include_license_key=True),
                                    json=retry_payload,
                                ) as retry_response:
                                    retry_data = await retry_response.json(content_type=None)
                                    if retry_response.status < 400:
                                        logging.info("Checkbox shift opened successfully after go-offline")
                                        return True
                                    logging.warning("Checkbox open shift failed after go-offline: %s", retry_data)

                        logging.warning("Checkbox open shift failed: %s", data)
                        return False
                    logging.info("Checkbox shift opened successfully")
                    return True
        except Exception as error:
            logging.warning("Checkbox open shift request error: %s", error)
            return False

    async def go_offline(self) -> bool:
        if not self.enabled:
            return False

        if not (self.config.payment.checkbox_license_key or "").strip():
            logging.warning("Checkbox go-offline skipped: CHECKBOX_LICENSE_KEY is empty")
            return False

        timeout = self.config.payment.checkbox_request_timeout_sec
        url = (
            f"{self.config.payment.checkbox_api_base_url.rstrip('/')}"
            f"{self.config.payment.checkbox_go_offline_endpoint}"
        )
        payload = self._go_offline_payload()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(url, headers=self._headers(include_license_key=True), json=payload) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        logging.warning("Checkbox go-offline failed: %s", data)
                        return False
                    logging.info("Checkbox switched to offline mode successfully")
                    return True
        except Exception as error:
            logging.warning("Checkbox go-offline request error: %s", error)
            return False

    async def close_shift(self) -> bool:
        if not self.enabled:
            return False

        if not (self.config.payment.checkbox_license_key or "").strip():
            logging.warning("Checkbox close shift skipped: CHECKBOX_LICENSE_KEY is empty")
            return False

        timeout = self.config.payment.checkbox_request_timeout_sec
        url = (
            f"{self.config.payment.checkbox_api_base_url.rstrip('/')}"
            f"{self.config.payment.checkbox_close_shift_endpoint}"
        )
        payload = self._close_shift_payload()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(url, headers=self._headers(include_license_key=True), json=payload) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        # If shift is already closed, treat this as success for daily close policy.
                        if self._is_shift_not_opened(data, data.get("code") if isinstance(data, dict) else None, str(data)):
                            logging.info("Checkbox shift already closed")
                            return True
                        logging.warning("Checkbox close shift failed: %s", data)
                        return False
                    logging.info("Checkbox shift closed successfully")
                    return True
        except Exception as error:
            logging.warning("Checkbox close shift request error: %s", error)
            return False

    def _normalize_status(self, value: Optional[str]) -> str:
        if not value:
            return "pending"
        status = value.strip().lower()
        if status in {"done", "closed", "success", "registered"}:
            return "success"
        if status in {"failed", "error", "canceled", "cancelled"}:
            return "failed"
        return "processing"

    def _parse_result(self, payload: dict) -> FiscalResult:
        receipt_id = payload.get("id") or payload.get("receipt_id") or payload.get("receiptId")
        receipt_url = payload.get("receipt_url") or payload.get("url") or payload.get("href")

        # Checkbox API does not return a receipt_url field — construct it from the receipt ID.
        if not receipt_url and receipt_id:
            template = (
                self.config.payment.checkbox_receipt_url_template
                or "https://check.checkbox.ua/{receipt_id}/html"
            )
            receipt_url = template.replace("{receipt_id}", str(receipt_id))

        pdf_url = payload.get("pdf_url") or payload.get("pdfUrl")

        status_raw = payload.get("status") or payload.get("state")
        status = self._normalize_status(status_raw)
        error_code = payload.get("code")
        error_text = payload.get("error") or payload.get("message")

        return FiscalResult(
            status=status,
            receipt_id=str(receipt_id) if receipt_id is not None else None,
            receipt_url=receipt_url,
            pdf_url=pdf_url,
            error_code=error_code,
            error_text=error_text,
            raw_payload=payload,
        )

    async def create_sale_receipt(self, payload: dict) -> FiscalResult:
        if not self.enabled:
            return FiscalResult(status="failed", error_text="Checkbox is disabled or token is missing")

        timeout = self.config.payment.checkbox_request_timeout_sec
        url = f"{self.config.payment.checkbox_api_base_url.rstrip('/')}{self.config.payment.checkbox_sell_endpoint}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=self._headers(), json=payload) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    result = FiscalResult(
                        status="failed",
                        error_code=(data.get("code") if isinstance(data, dict) else None),
                        error_text=f"Checkbox create receipt error: {data}",
                        raw_payload=data,
                    )

                    # Auto-heal: if cashier shift is closed, try to open it and retry once.
                    if self._is_shift_not_opened(data, result.error_code, result.error_text):
                        opened = await self.open_shift()
                        if opened:
                            async with session.post(url, headers=self._headers(), json=payload) as retry_response:
                                retry_data = await retry_response.json(content_type=None)
                                if retry_response.status < 400:
                                    return self._parse_result(retry_data)
                                return FiscalResult(
                                    status="failed",
                                    error_code=(retry_data.get("code") if isinstance(retry_data, dict) else None),
                                    error_text=f"Checkbox create receipt error after open_shift retry: {retry_data}",
                                    raw_payload=retry_data,
                                )

                    return result
                return self._parse_result(data)

    async def get_receipt_status(self, receipt_id: str) -> FiscalResult:
        if not self.enabled:
            return FiscalResult(status="failed", error_text="Checkbox is disabled or token is missing")

        timeout = self.config.payment.checkbox_request_timeout_sec
        endpoint = self.config.payment.checkbox_status_endpoint.format(receipt_id=receipt_id)
        url = f"{self.config.payment.checkbox_api_base_url.rstrip('/')}{endpoint}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url, headers=self._headers()) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    return FiscalResult(
                        status="failed",
                        error_code=(data.get("code") if isinstance(data, dict) else None),
                        error_text=f"Checkbox receipt status error: {data}",
                        raw_payload=data,
                    )
                return self._parse_result(data)
