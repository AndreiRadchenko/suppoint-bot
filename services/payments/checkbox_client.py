import aiohttp
from dataclasses import dataclass
from typing import Optional

from config_data.config import Config


@dataclass
class FiscalResult:
    status: str
    receipt_id: Optional[str] = None
    receipt_url: Optional[str] = None
    pdf_url: Optional[str] = None
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

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._resolve_token()}",
            "Content-Type": "application/json",
        }

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
        pdf_url = payload.get("pdf_url") or payload.get("pdfUrl")

        status_raw = payload.get("status") or payload.get("state")
        status = self._normalize_status(status_raw)
        error_text = payload.get("error") or payload.get("message")

        return FiscalResult(
            status=status,
            receipt_id=str(receipt_id) if receipt_id is not None else None,
            receipt_url=receipt_url,
            pdf_url=pdf_url,
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
                    return FiscalResult(
                        status="failed",
                        error_text=f"Checkbox create receipt error: {data}",
                        raw_payload=data,
                    )
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
                        error_text=f"Checkbox receipt status error: {data}",
                        raw_payload=data,
                    )
                return self._parse_result(data)
