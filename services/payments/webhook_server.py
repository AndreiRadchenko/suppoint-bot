import asyncio
import contextlib

from aiohttp import web

from config_data.config import Config, load_config
from .payment_service import PaymentService


class MonobankWebhookServer:
    def __init__(self, payment_service: PaymentService):
        self.config: Config = load_config()
        self.payment_service = payment_service
        self._runner = None
        self._site = None
        self._reconcile_task = None

    async def start(self):
        app = web.Application()
        app.router.add_post(self.config.payment.mono_webhook_path, self.handle_webhook)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner,
            self.config.payment.mono_webhook_host,
            self.config.payment.mono_webhook_port,
        )
        await self._site.start()

        self._reconcile_task = asyncio.create_task(self._reconcile_loop())

    async def stop(self):
        if self._reconcile_task:
            self._reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconcile_task
        if self._runner:
            await self._runner.cleanup()

    async def _reconcile_loop(self):
        while True:
            await asyncio.sleep(max(10, int(self.config.payment.fiscal_retry_interval_sec)))
            await self.payment_service.enforce_checkbox_shift_policy()
            await self.payment_service.reconcile_pending_transactions()
            await self.payment_service.reconcile_fiscal_transactions()

    async def handle_webhook(self, request: web.Request) -> web.Response:
        raw_body = await request.read()
        x_sign = request.headers.get("X-Sign", "")
        if not x_sign:
            return web.Response(status=400, text="Missing X-Sign")

        verified = await self.payment_service.verify_webhook_signature(raw_body, x_sign)
        if not verified:
            return web.Response(status=401, text="Invalid signature")

        try:
            payload = await request.json()
            print("Received webhook payload:", payload)
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        await self.payment_service.process_webhook_payload(payload, raw_body)
        return web.Response(status=200, text="OK")
