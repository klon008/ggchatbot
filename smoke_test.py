"""Дымовой тест: HTTP-раздача player.html + WebSocket-цикл очереди.

Проверяет обвязку без чата GoodGame:
  1. Сервер отдаёт player.html и player.js по HTTP.
  2. Клиент подключается по WS, шлёт ready.
  3. В очередь кладём 2 трека, бот шлёт play (token=t-1).
  4. Клиент отвечает ended(t-1) -> бот шлёт play второго (t-2).
  5. Устаревший ended(t-1) игнорируется (проверка защиты от двойного скипа).
"""
import asyncio
import sys
import time

import aiohttp

from bot.app import SongRequestBot
from bot.song_request import Track
from config import Config


async def main() -> int:
    cfg = Config.load()
    cfg.gg_channel_id = ""  # не подключаемся к GG
    cfg.obs_port = 18765
    bot = SongRequestBot(cfg)
    await bot.db.open()
    await bot.queue.clear()
    bot.sr.bind_points(bot.princess.points)
    await bot.obs.start()

    base = f"http://{cfg.obs_host}:{cfg.obs_port}"
    ok = True
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/player.html") as r:
            html = await r.text()
            assert r.status == 200 and "player.js" in html, "player.html не отдался"
            print("[OK] HTTP player.html")
        async with s.get(f"{base}/player.js") as r:
            assert r.status == 200, "player.js не отдался"
            print("[OK] HTTP player.js")

        async def wait_action(ws, action, timeout=3):
            """Дождаться сообщения с нужным action (пропуская прочие)."""
            loop = asyncio.get_event_loop()
            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise asyncio.TimeoutError(f"нет сообщения action={action}")
                m = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
                if m.get("action") == action:
                    return m

        async with s.ws_connect(f"{base}/ws") as ws:
            await ws.send_json({"status": "ready"})
            await asyncio.sleep(0.2)

            # Кладём два трека; ready при пустой очереди прислал queue_state.
            await bot.queue.add(Track(video_id="aaaaaaaaaaa", requested_by="u1", url="x"))
            await bot.queue.add(Track(video_id="bbbbbbbbbbb", requested_by="u2", url="y"))
            await bot._advance(expected_token=None)

            msg = await wait_action(ws, "play")
            assert msg["videoId"] == "aaaaaaaaaaa", msg
            t1 = msg["token"]
            print(f"[OK] play #1 token={t1}")

            # Завершаем первый -> должен прийти второй.
            await ws.send_json({"status": "ended", "token": t1})
            msg = await wait_action(ws, "play")
            assert msg["videoId"] == "bbbbbbbbbbb", msg
            t2 = msg["token"]
            print(f"[OK] play #2 token={t2}")

            # Устаревший ended(t1) должен игнорироваться (не проматывать).
            await ws.send_json({"status": "ended", "token": t1})
            try:
                extra = await asyncio.wait_for(ws.receive_json(), timeout=1)
                print(f"[FAIL] устаревший token вызвал реакцию: {extra}")
                ok = False
            except asyncio.TimeoutError:
                print("[OK] устаревший token проигнорирован")

            # Завершаем второй -> очередь пуста -> queue_state.
            await ws.send_json({"status": "ended", "token": t2})
            msg = await wait_action(ws, "queue_state")
            assert not msg["playing"], msg
            print("[OK] очередь пуста -> queue_state")

            # --- Возврат принцесс при ошибке плеера ----------------------
            refund_uid = "smoke-refund-user"
            await bot.princess.points.set_balance(refund_uid, 0)
            await bot.queue.clear()
            await bot.queue.add(
                Track(
                    video_id="ddddddddddd",
                    requested_by=refund_uid,
                    requested_by_name="RefundUser",
                    url="z",
                    paid_cost=100,
                )
            )
            await bot._advance(expected_token=None)
            msg = await wait_action(ws, "play")
            refund_token = msg["token"]
            await bot.sr._on_obs_status(
                {
                    "status": "error",
                    "token": refund_token,
                    "videoId": "ddddddddddd",
                    "code": 100,
                    "message": "видео удалено или приватное",
                }
            )
            refunded = await bot.princess.points.get_balance(refund_uid)
            assert refunded == 100, f"ожидали возврат 100, баланс={refunded}"
            print("[OK] возврат принцесс при error")

        # --- Admin API ---------------------------------------------------
        async with s.get(f"{base}/admin.html") as r:
            html = await r.text()
            assert r.status == 200 and "admin.js" in html, "admin.html не отдался"
            print("[OK] HTTP admin.html")
        async with s.get(f"{base}/admin.js") as r:
            assert r.status == 200, "admin.js не отдался"
            print("[OK] HTTP admin.js")

        test_uid = f"smoke-test-{int(time.time())}"
        async with s.post(
            f"{base}/api/points",
            json={"user_id": test_uid, "balance": 42},
        ) as r:
            assert r.status == 201, await r.text()
            print("[OK] POST /api/points")

        async with s.get(f"{base}/api/points") as r:
            data = await r.json()
            assert any(p["user_id"] == test_uid and p["balance"] == 42 for p in data["items"])
            print("[OK] GET /api/points")

        async with s.put(
            f"{base}/api/points/{test_uid}",
            json={"balance": 100},
        ) as r:
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["balance"] == 100
            print("[OK] PUT /api/points")

        await bot.queue.add(Track(video_id="ccccccccccc", requested_by="u3", url="z", title="Smoke"))
        async with s.get(f"{base}/api/queue") as r:
            qdata = await r.json()
            assert len(qdata["waiting"]) == 1
            assert qdata["waiting"][0]["video_id"] == "ccccccccccc"
            print("[OK] GET /api/queue")

        async with s.delete(f"{base}/api/queue/waiting/0") as r:
            assert r.status == 200, await r.text()
            print("[OK] DELETE /api/queue/waiting/0")

        async with s.get(f"{base}/api/queue") as r:
            qdata = await r.json()
            assert len(qdata["waiting"]) == 0
            print("[OK] queue empty after delete")

        async with s.delete(f"{base}/api/points/{test_uid}") as r:
            assert r.status == 200, await r.text()
            print("[OK] DELETE /api/points")

    if bot._watchdog:
        bot._watchdog.cancel()
    await bot.queue.clear()
    await bot.obs.stop()
    await bot.db.close()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
