import aiohttp


class MonobankClient:
    BASE_URL = "https://api.monobank.ua"

    def __init__(self, token: str):
        self.token = token

    @property
    def _headers(self):
        return {
            "X-Token": self.token,
            "Content-Type": "application/json",
        }

    async def create_invoice(self, payload: dict) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/api/merchant/invoice/create",
                headers=self._headers,
                json=payload,
                timeout=20,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise RuntimeError(f"Monobank create_invoice error: {data}")
                return data

    async def get_invoice_status(self, invoice_id: str) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/api/merchant/invoice/status",
                headers=self._headers,
                params={"invoiceId": invoice_id},
                timeout=20,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise RuntimeError(f"Monobank get_invoice_status error: {data}")
                return data

    async def get_public_key(self) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/api/merchant/pubkey",
                headers=self._headers,
                timeout=20,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise RuntimeError(f"Monobank get_public_key error: {data}")
                return data["key"]
