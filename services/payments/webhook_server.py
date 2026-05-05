import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import urllib.parse
from pathlib import Path

from aiohttp import web
from aiogram.types import BufferedInputFile
from aiogram.fsm.storage.base import StorageKey

from config_data.config import Config, load_config
from .payment_service import PaymentService
from create_bot import bot as _tg_bot, storage as _fsm_storage

# FSM state key for RentFinishFSM.waiting_for_confirmation (aiogram 3 format).
_RENT_FINISH_CONFIRM_STATE = "RentFinishFSM:waiting_for_confirmation"

_PHOTO_PAGE_PATH = Path(__file__).parent.parent.parent / "media" / "photo_upload.html"


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
        app.router.add_get("/rent-photo", self.handle_rent_photo_page)
        app.router.add_post("/api/upload-rent-photo", self.handle_photo_upload)

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

    # ------------------------------------------------------------------
    # Web App: serve photo-upload page
    # ------------------------------------------------------------------

    async def handle_rent_photo_page(self, request: web.Request) -> web.Response:
        try:
            html = _PHOTO_PAGE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return web.Response(status=404, text="Not found")
        return web.Response(content_type="text/html", text=html)

    def _validate_webapp_init_data(self, init_data: str) -> dict | None:
        """Validate Telegram Web App initData HMAC signature."""
        if not init_data:
            return None
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        hash_val = parsed.pop("hash", "")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", self.config.tg_bot.token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val):
            return None
        return parsed

    async def handle_photo_upload(self, request: web.Request) -> web.Response:
        """Receive photo from the Web App, forward to admins, update DB, advance FSM."""
        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid multipart"}, status=400)

        photo_bytes: bytes | None = None
        filename = "photo.jpg"
        rent_id: str | None = None
        init_data: str | None = None

        async for field in reader:
            if field.name == "photo":
                filename = field.filename or "photo.jpg"
                photo_bytes = await field.read()
                if len(photo_bytes) > 10 * 1024 * 1024:
                    return web.json_response({"ok": False, "error": "File too large"}, status=413)
            elif field.name == "rent_id":
                rent_id = (await field.read()).decode("utf-8", errors="ignore").strip()
            elif field.name == "init_data":
                init_data = (await field.read()).decode("utf-8", errors="ignore")

        if not photo_bytes:
            return web.json_response({"ok": False, "error": "No photo"}, status=400)
        if not rent_id:
            return web.json_response({"ok": False, "error": "No rent_id"}, status=400)

        # Validate Telegram Web App init_data.
        parsed = self._validate_webapp_init_data(init_data or "")
        if parsed is None:
            return web.json_response({"ok": False, "error": "Invalid auth"}, status=401)

        try:
            user_data = json.loads(parsed.get("user", "{}"))
            tg_id = int(user_data["id"])
        except (KeyError, ValueError, TypeError):
            return web.json_response({"ok": False, "error": "No user"}, status=400)

        db = self.payment_service.db
        rent = db.get_rent_by_id(rent_id)
        if not rent or int(rent[1]) != tg_id:
            return web.json_response({"ok": False, "error": "Rent not found"}, status=404)

        locker = db.get_locker_by_locker_id(rent[3])
        locker_number = locker[2] if locker else "?"
        station = db.get_station_by_id(rent[2]) if rent[2] else None
        station_location = (station[2] or "").strip() if station else f"#{rent[2]}"
        start_time = rent[11] or "Невідомо"

        admin_caption = (
            f"Комплектація до завершення Оренди {rent_id}\n"
            f"Локація: {station_location}\n"
            f"Комірка: {locker_number}\n"
            f"Початок оренди: {start_time}"
        )

        # Send to first admin to obtain a Telegram file_id.
        admin_ids = self.config.tg_bot.admin_ids
        photo_input = BufferedInputFile(photo_bytes, filename=filename)
        first_msg = await _tg_bot.send_photo(admin_ids[0], photo_input, caption=admin_caption)
        file_id = first_msg.photo[-1].file_id

        # Forward to remaining admins by file_id (no re-upload needed).
        for admin_id in admin_ids[1:]:
            try:
                await _tg_bot.send_photo(admin_id, file_id, caption=admin_caption)
            except Exception as exc:
                logging.warning("Failed to forward rent photo to admin %s: %s", admin_id, exc)

        # Echo photo back to user so it appears in their chat.
        await _tg_bot.send_photo(tg_id, file_id)

        # Persist photo in DB.
        db.rent_update_complect_photo("photo", file_id, rent_id)

        # Advance FSM to waiting_for_confirmation so the user can tap the finish button.
        bot_me = await _tg_bot.get_me()
        storage_key = StorageKey(bot_id=bot_me.id, chat_id=tg_id, user_id=tg_id)
        await _fsm_storage.set_state(key=storage_key, state=_RENT_FINISH_CONFIRM_STATE)
        await _fsm_storage.set_data(key=storage_key, data={
            "rent_id": rent_id,
            "locker_id": str(rent[3]),
            "file_type": "photo",
            "file_id": file_id,
        })

        # Notify user with the confirmation button.
        from kb import kb
        await _tg_bot.send_message(
            tg_id,
            "✅ Фото збережено!\n\nТепер закрийте дверцята комірки та натисніть кнопку нижче:",
            reply_markup=kb.rent_finish_confirm_menu,
        )

        return web.json_response({"ok": True})
