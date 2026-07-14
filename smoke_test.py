"""Дымовой тест: HTTP-раздача player.html + WebSocket-цикл очереди.

Проверяет обвязку без чата GoodGame:
  1. Сервер отдаёт player.html и player.js по HTTP.
  2. Клиент подключается по WS, шлёт ready.
  3. В очередь кладём 2 трека, бот шлёт play (token=t-1).
  4. Клиент отвечает ended(t-1) -> бот шлёт play второго (t-2).
  5. Устаревший ended(t-1) игнорируется (проверка защиты от двойного скипа).
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import aiohttp

from bot import StreamBot
from bot.commands import PUBLIC_COMMANDS
from bot.db import users as users_db
from bot.db import minigames_bank
from bot.db import roulette as roulette_db
from bot.goodgame import ChatMessage
from bot.races import bets as races_bets
from bot.races import odds as races_odds
from bot.roulette import bets as roulette_bets
from bot.song_request import Track
from config import Config


def find_main_py_pids() -> list[int]:
    """PID процессов Python, запущенных с main.py (не smoke_test)."""
    if sys.platform == "win32":
        ps_script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and "
            "($_.CommandLine -match 'main\\.py') -and "
            "($_.CommandLine -notmatch 'smoke_test\\.py') } | "
            "ForEach-Object { $_.ProcessId }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]

    try:
        result = subprocess.run(
            ["pgrep", "-f", r"main\.py"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    own_pid = str(os.getpid())
    pids: list[int] = []
    for line in result.stdout.splitlines():
        pid = line.strip()
        if pid.isdigit() and pid != own_pid:
            pids.append(int(pid))
    return pids


def ensure_main_not_running() -> None:
    pids = find_main_py_pids()
    if not pids:
        return
    print("[SKIP] Основной бот (main.py) уже запущен.")
    print(f"       PID: {', '.join(map(str, pids))}")
    print("       Закройте окно start.cmd и повторите smoke_test.")
    sys.exit(2)


async def main() -> int:
    assert "!заказ" in PUBLIC_COMMANDS
    assert "!рулетка" in PUBLIC_COMMANDS
    assert "!забег" in PUBLIC_COMMANDS
    assert "!бустер" in PUBLIC_COMMANDS
    assert "!альбом" in PUBLIC_COMMANDS
    assert "!пропуск" not in PUBLIC_COMMANDS
    assert "!списать" not in PUBLIC_COMMANDS
    assert "!рулетка_банк" not in PUBLIC_COMMANDS
    print("[OK] PUBLIC_COMMANDS")
    cfg = Config.load()
    cfg.gg_channel_id = ""  # не подключаемся к GG
    cfg.obs_port = 18765
    cfg.album_link_secret = "smoke-test-album-secret-32b!!!!"
    cfg.clo_public_url = "http://127.0.0.1:18770"
    tmp_db = Path(tempfile.gettempdir()) / f"smoke-botmsc-{int(time.time())}.db"
    for path in (tmp_db, Path(str(tmp_db) + "-wal"), Path(str(tmp_db) + "-shm")):
        if path.exists():
            path.unlink()
    bot = StreamBot(cfg, db_path=tmp_db)
    await bot.db.open()
    bot.sr.bind_points(bot.princess.points)
    await bot.sr.start()
    await bot.roulette.start()
    await bot.races.start()
    bot.roulette.bind_points(bot.princess.points)
    bot.races.bind_points(bot.princess.points)

    async def fake_online_users() -> list[dict]:
        return [{"id": "smoke-sync-user", "name": "SyncedUser"}]

    bot.admin.bind_user_names(fake_online_users, bot.princess.points)
    await bot.princess.points.load()
    await bot.sr.queue.clear()
    await bot.sr.set_orders_enabled(True)
    await bot.web.start()
    await bot.album_web.start()
    await bot.clo.start()
    bot.cards.bind_points(bot.princess.points)

    album_base = "http://127.0.0.1:18770"
    ok = True
    base = f"http://{cfg.obs_host}:{cfg.obs_port}"
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/player.html") as r:
            html = await r.text()
            assert r.status == 200 and "player.js" in html, "player.html не отдался"
            print("[OK] HTTP player.html")
        async with s.get(f"{base}/player.js") as r:
            assert r.status == 200, "player.js не отдался"
            print("[OK] HTTP player.js")

        async with s.get(f"{album_base}/api/v1/health") as r:
            assert r.status == 200, await r.text()
            print("[OK] GET /api/v1/health (album)")

        from urllib.parse import parse_qs, urlparse

        from bot.cards.album_token import build_album_url

        await bot.princess.points.touch_name_if_new("album-smoke", "smokeplayer")
        link = build_album_url(
            site_base_url=cfg.site_base_url,
            link_secret=cfg.album_link_secret,
            nick="smokeplayer",
            api_base_url=album_base,
        )
        qs = parse_qs(urlparse(link).query)
        async with s.get(
            f"{album_base}/api/v1/album",
            params={"u": qs["u"][0], "k": qs["k"][0], "exp": qs["exp"][0]},
        ) as r:
            assert r.status == 200, await r.text()
            data = await r.json()
            assert data["collection"]["total"] == 28
            print("[OK] GET /api/v1/album")

        async with s.get(f"{album_base}/api/v1/album", params={"u": "x", "k": "bad", "exp": "1"}) as r:
            assert r.status == 401
            print("[OK] GET /api/v1/album invalid token")

        async with s.get(f"{base}/api/cards/catalog") as r:
            assert r.status == 200, await r.text()
            catalog = await r.json()
            assert len(catalog["items"]) == 28
            assert any(c["id"] == "elsa" and c["rarity"] == "mythic" for c in catalog["items"])
            assert any(
                c.get("image_url") == "/assets/cards/anna.webp" for c in catalog["items"]
            )
            print("[OK] GET /api/cards/catalog")

        async with s.get(f"{base}/api/cards/boosters") as r:
            assert r.status == 200
            boosters = await r.json()
            assert any(b["id"] == "start" and b["name"] == "Стартовый набор" for b in boosters["items"])
            print("[OK] GET /api/cards/boosters")

        async with s.get(f"{base}/api/cards/draws") as r:
            assert r.status == 200
            draws = await r.json()
            assert any(d["status"] == "active" for d in draws["items"])
            print("[OK] GET /api/cards/draws")

        async with s.put(f"{base}/api/cards/meta", json={"daily_open_limit": 5}) as r:
            assert r.status == 200
            print("[OK] PUT /api/cards/meta")

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
            await bot.sr.queue.add(Track(video_id="aaaaaaaaaaa", requested_by="u1", url="x"))
            await bot.sr.queue.add(Track(video_id="bbbbbbbbbbb", requested_by="u2", url="y"))
            await bot.sr.advance(expected_token=None)

            msg = await wait_action(ws, "play")
            assert msg["videoId"] == "aaaaaaaaaaa", msg
            t1 = msg["token"]
            print(f"[OK] play #1 token={t1}")

            async with s.post(f"{base}/api/queue/toggle-pause") as r:
                assert r.status == 200, await r.text()
                body = await r.json()
                assert body["paused"] is True, body
            msg = await wait_action(ws, "toggle_pause")
            assert msg.get("token") == t1, msg
            print("[OK] POST /api/queue/toggle-pause -> paused")

            async with s.post(f"{base}/api/queue/toggle-pause") as r:
                assert r.status == 200, await r.text()
                body = await r.json()
                assert body["paused"] is False, body
            msg = await wait_action(ws, "toggle_pause")
            assert msg.get("token") == t1, msg
            print("[OK] POST /api/queue/toggle-pause -> resumed")

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

            async with s.post(f"{base}/api/queue/toggle-pause") as r:
                assert r.status == 409, await r.text()
            print("[OK] POST /api/queue/toggle-pause 409 when idle")

            # --- Возврат принцесс при ошибке плеера ----------------------
            refund_uid = "smoke-refund-user"
            await bot.princess.points.set_balance(refund_uid, 0)
            await bot.sr.queue.clear()
            await bot.sr.queue.add(
                Track(
                    video_id="ddddddddddd",
                    requested_by=refund_uid,
                    requested_by_name="RefundUser",
                    url="z",
                    paid_cost=100,
                )
            )
            await bot.sr.advance(expected_token=None)
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

        pending_uid = "smoke-pending-user"
        await bot.princess.points.set_balance(pending_uid, 0)
        await bot.princess.points.add(pending_uid, 10)
        pending_balance = await bot.princess.points.get_balance(pending_uid)
        assert pending_balance == 10, f"ожидали pending 10, баланс={pending_balance}"
        row = await bot.db.fetchone(
            "SELECT balance FROM points WHERE user_id = ?",
            (pending_uid,),
        )
        assert row is not None and int(row["balance"]) == 0, "pending не должен быть в БД до flush"
        await bot.princess.points.flush()
        row = await bot.db.fetchone(
            "SELECT balance FROM points WHERE user_id = ?",
            (pending_uid,),
        )
        assert row is not None and int(row["balance"]) == 10, "после flush баланс должен быть 10"
        print("[OK] points pending + flush")
        await bot.princess.points.apply_income_tick([pending_uid], 3)
        row = await bot.db.fetchone(
            "SELECT balance FROM points WHERE user_id = ?",
            (pending_uid,),
        )
        assert row is not None and int(row["balance"]) == 13, "после income tick баланс должен быть 13"
        print("[OK] points apply_income_tick")

        admin_conflict_uid = "smoke-admin-pending"
        await bot.princess.points.set_balance(admin_conflict_uid, 0)
        await bot.princess.points.add(admin_conflict_uid, 50)
        async with s.put(
            f"{base}/api/points/{admin_conflict_uid}",
            json={"balance": 1000},
        ) as r:
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["balance"] == 1000, body
        balance = await bot.princess.points.get_balance(admin_conflict_uid)
        assert balance == 1000, f"ожидали 1000 после admin PUT, баланс={balance}"
        await bot.princess.points.flush()
        row = await bot.db.fetchone(
            "SELECT balance FROM points WHERE user_id = ?",
            (admin_conflict_uid,),
        )
        assert row is not None and int(row["balance"]) == 1000, (
            "pending не должен перезаписать правку админки после flush"
        )
        print("[OK] admin PUT сбрасывает pending, flush не перезаписывает")

        test_uid = f"smoke-test-{int(time.time())}"
        async with s.post(
            f"{base}/api/points",
            json={"user_id": test_uid, "balance": 42, "user_name": "SmokeNick"},
        ) as r:
            assert r.status == 201, await r.text()
            body = await r.json()
            assert body.get("user_name") == "SmokeNick", body
            print("[OK] POST /api/points")

        async with s.get(f"{base}/api/points") as r:
            data = await r.json()
            assert any(
                p["user_id"] == test_uid
                and p["balance"] == 42
                and p.get("user_name") == "SmokeNick"
                for p in data["items"]
            )
            print("[OK] GET /api/points (user_name)")

        touch_uid = "smoke-touch-user"
        await bot.princess.points.set_balance(touch_uid, 10)
        assert await bot.princess.points.touch_name_if_new(touch_uid, "TouchUser")
        assert not await bot.princess.points.touch_name_if_new(touch_uid, "Renamed")
        async with s.get(f"{base}/api/points") as r:
            data = await r.json()
            assert any(
                p["user_id"] == touch_uid and p.get("user_name") == "TouchUser"
                for p in data["items"]
            )
            print("[OK] touch_name_if_new в API")
        await bot.princess.points.set_balance(touch_uid, 0)
        row = await bot.db.fetchone("SELECT 1 FROM points WHERE user_id = ?", (touch_uid,))
        if row:
            await bot.db.execute("DELETE FROM points WHERE user_id = ?", (touch_uid,))

        async with s.put(
            f"{base}/api/points/{test_uid}",
            json={"balance": 100},
        ) as r:
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["balance"] == 100
            print("[OK] PUT /api/points")

        async with s.post(f"{base}/api/user-names/sync") as r:
            assert r.status == 200, await r.text()
            sync_body = await r.json()
            assert sync_body["updated"] == 1
            assert sync_body["total_online"] == 1
            print("[OK] POST /api/user-names/sync")

        synced_name = await users_db.get_user_name(bot.db, "smoke-sync-user")
        assert synced_name == "SyncedUser", synced_name
        print("[OK] sync user_name в БД")

        await bot.sr.queue.add(Track(video_id="ccccccccccc", requested_by="u3", url="z", title="Smoke"))
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

        disable_uid = "smoke-disable-user"
        await bot.princess.points.set_balance(disable_uid, 0)
        await bot.sr.queue.clear()
        await bot.sr.queue.add(
            Track(
                video_id="eeeeeeeeeee",
                requested_by=disable_uid,
                requested_by_name="DisableUser",
                url="w",
                paid_cost=100,
            )
        )
        async with s.put(
            f"{base}/api/song-request",
            json={"orders_enabled": False},
        ) as r:
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["orders_enabled"] is False
            print("[OK] PUT /api/song-request (disable)")
        refunded = await bot.princess.points.get_balance(disable_uid)
        assert refunded == 100, f"ожидали возврат 100 при отключении, баланс={refunded}"
        print("[OK] возврат принцесс при отключении заказов")
        async with s.get(f"{base}/api/queue") as r:
            qdata = await r.json()
            assert qdata["playing"] is None
            assert len(qdata["waiting"]) == 0
            print("[OK] очередь пуста после отключения заказов")
        async with s.put(
            f"{base}/api/song-request",
            json={"orders_enabled": True},
        ) as r:
            assert r.status == 200, await r.text()
            print("[OK] PUT /api/song-request (enable)")

        # --- Roulette ---
        nums18 = ",".join(str(i) for i in range(18))
        parsed18 = roulette_bets.parse_bet_command(f"!рулетка 100 на {nums18}")
        assert not isinstance(parsed18, roulette_bets.ParseError), parsed18
        parsed19 = roulette_bets.parse_bet_command(
            "!рулетка 100 на " + ",".join(str(i) for i in range(19))
        )
        assert isinstance(parsed19, roulette_bets.ParseError)
        assert "18" in parsed19.message
        dup_nums = roulette_bets.parse_bet_command("!рулетка 100 на 1,1")
        assert isinstance(dup_nums, roulette_bets.ParseError)
        parsed_short = roulette_bets.parse_bet_command("!рулетка 500 15")
        assert not isinstance(parsed_short, roulette_bets.ParseError), parsed_short
        assert parsed_short.bet_payload["numbers"] == [15]
        print("[OK] roulette bet parsing")

        async with s.get(f"{base}/api/roulette") as r:
            assert r.status == 200, await r.text()
            rdata = await r.json()
            assert rdata["state"] == "IDLE"
            assert rdata["bank"] >= 5000
            print("[OK] GET /api/roulette")

        async with s.get(f"{base}/roulette.html") as r:
            assert r.status == 200
            body = await r.text()
            assert "wheelRotor" in body
            print("[OK] GET /roulette.html")

        r_user = "smoke-roulette-user"
        await bot.princess.points.set_balance(r_user, 10_000)
        await bot.princess.points.flush()

        msg = ChatMessage(
            channel_id="",
            user_id=r_user,
            user_name="RouletteUser",
            user_rights=0,
            text="!рулетка 200 красное",
        )
        assert await bot.roulette.handle_message(msg)
        status = await bot.roulette.get_status()
        assert status["state"] == "OPEN"
        assert len(status["bets"]) == 1
        balance_after = await bot.princess.points.get_balance(r_user)
        assert balance_after == 9800, balance_after
        print("[OK] roulette auto open + bet")

        dup_msg = ChatMessage(
            channel_id="",
            user_id=r_user,
            user_name="RouletteUser",
            user_rights=0,
            text="!рулетка 100 черное",
        )
        assert await bot.roulette.handle_message(dup_msg)
        balance_dup = await bot.princess.points.get_balance(r_user)
        assert balance_dup == 9800, balance_dup
        status = await bot.roulette.get_status()
        assert len(status["bets"]) == 1
        print("[OK] roulette duplicate bet rejected")

        with patch("bot.roulette.round.wheel.spin", return_value=1):
            await bot.roulette.admin_spin()
        status = await bot.roulette.get_status()
        assert status["state"] == "COOLDOWN"
        assert status["last_result"] is not None
        print("[OK] roulette spin")

        await minigames_bank.set_bank(bot.db, 5000)
        await roulette_db.update_meta(bot.db, state="IDLE", cooldown_until=None)
        await bot.princess.points.set_balance("smoke-bankrupt-user", 5000)
        await bot.princess.points.flush()
        bmsg = ChatMessage(
            channel_id="",
            user_id="smoke-bankrupt-user",
            user_name="BankruptUser",
            user_rights=0,
            text="!рулетка 200 на 7",
        )
        assert await bot.roulette.handle_message(bmsg)
        status = await bot.roulette.get_status()
        assert status["state"] == "OPEN", status
        with patch("bot.roulette.round.wheel.spin", return_value=7):
            await bot.roulette.admin_spin()
        status = await bot.roulette.get_status()
        assert status["bank"] == 0, status
        assert status["last_result"]["bankrupted"] is True
        print("[OK] roulette bank bankruptcy")

        await minigames_bank.set_bank(bot.db, 50_000)
        await roulette_db.update_meta(bot.db, state="IDLE", cooldown_until=None)
        async with s.put(
            f"{base}/api/roulette",
            json={"auto_enabled": False, "collect_sec": 30, "cooldown_sec": 60},
        ) as r:
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["auto_enabled"] is False
            print("[OK] PUT /api/roulette")

        async with s.post(f"{base}/api/roulette/open") as r:
            assert r.status == 200, await r.text()
            print("[OK] POST /api/roulette/open")

        async with s.post(f"{base}/api/roulette/cancel") as r:
            assert r.status == 200, await r.text()
            cancel_body = await r.json()
            assert cancel_body["state"] == "IDLE"
            print("[OK] POST /api/roulette/cancel")

        async with s.post(f"{base}/api/roulette/bank", json={"amount": 1000}) as r:
            assert r.status == 200, await r.text()
            print("[OK] POST /api/roulette/bank")

        # --- Races ---
        from bot.db import races as races_db
        from bot.races import simulate as races_simulate

        parsed_races = races_bets.parse_bet_command("!забег 150 3")
        assert not isinstance(parsed_races, races_bets.ParseError), parsed_races
        bad_horse = races_bets.parse_bet_command("!забег 100 7")
        assert isinstance(bad_horse, races_bets.ParseError)
        print("[OK] races bet parsing")

        async with s.get(f"{base}/api/races") as r:
            assert r.status == 200, await r.text()
            races_data = await r.json()
            assert races_data["state"] == "IDLE"
            assert races_data["bank"] >= 5000
            assert len(races_data.get("princess_stats", [])) == 21
            assert races_data["princess_stats"][0]["princess_name"]
            print("[OK] GET /api/races")

        async with s.get(f"{base}/races.html") as r:
            assert r.status == 200
            body = await r.text()
            assert "raceWrap" in body
            print("[OK] GET /races.html")

        async with s.get(f"{base}/assets/princesses/elza.svg") as r:
            assert r.status == 200, await r.text()
            print("[OK] GET /assets/princesses/elza.svg")

        race_user = "smoke-races-user"
        await bot.princess.points.set_balance(race_user, 10_000)
        await bot.princess.points.flush()

        idle_bet_msg = ChatMessage(
            channel_id="",
            user_id="smoke-races-idle-bet",
            user_name="IdleBetUser",
            user_rights=0,
            text="!забег 50 1",
        )
        await bot.princess.points.set_balance("smoke-races-idle-bet", 1000)
        await bot.princess.points.flush()
        assert await bot.races.handle_message(idle_bet_msg)
        assert await bot.princess.points.get_balance("smoke-races-idle-bet") == 1000
        print("[OK] races bet rejected in IDLE")

        open_msg = ChatMessage(
            channel_id="",
            user_id=race_user,
            user_name="RacesUser",
            user_rights=0,
            text="!забег",
        )
        assert await bot.races.handle_message(open_msg)
        race_status = await bot.races.get_status()
        assert race_status["state"] == "OPEN"
        assert len(race_status["bets"]) == 0
        assert len(race_status["lineup"]) == 6
        assert await bot.princess.points.get_balance(race_user) == 10_000
        print("[OK] races open shows lineup without bet")

        race_msg = ChatMessage(
            channel_id="",
            user_id=race_user,
            user_name="RacesUser",
            user_rights=0,
            text="!забег 200 1",
        )
        assert await bot.races.handle_message(race_msg)
        race_status = await bot.races.get_status()
        assert race_status["state"] == "OPEN"
        assert len(race_status["bets"]) == 1
        race_balance = await bot.princess.points.get_balance(race_user)
        assert race_balance == 9800, race_balance
        print("[OK] races bet after open")

        dup_race_msg = ChatMessage(
            channel_id="",
            user_id=race_user,
            user_name="RacesUser",
            user_rights=0,
            text="!забег 100 2",
        )
        assert await bot.races.handle_message(dup_race_msg)
        assert await bot.princess.points.get_balance(race_user) == 9800
        print("[OK] races duplicate bet rejected")

        entries = await races_db.get_lineup(bot.db, race_status["round_id"])
        bet_list = await races_db.list_bets(bot.db, race_status["round_id"])
        computed_odds = await races_odds.compute_odds(bot.db, entries, bet_list)
        assert 1 in computed_odds and computed_odds[1] >= 1.1
        print("[OK] races odds")

        async def _noop_sleep(_sec: float) -> None:
            return None

        fake_result = races_simulate.RaceResult(
            winner_horse=1,
            winner_name=entries[0].princess_name,
            finish_order=[e.horse_number for e in entries],
            ticks=[],
            events=[],
        )
        with patch("bot.races.round.simulate.simulate_race", return_value=fake_result):
            with patch("bot.races.round.asyncio.sleep", _noop_sleep):
                await bot.races.admin_start()
        race_status = await bot.races.get_status()
        assert race_status["state"] == "COOLDOWN"
        assert race_status["last_result"] is not None
        stats_by_name = {s["princess_name"]: s for s in race_status["princess_stats"]}
        winner_name = entries[0].princess_name
        assert stats_by_name[winner_name]["wins_count"] >= 1
        print("[OK] races finish + payouts")

        await minigames_bank.set_bank(bot.db, 50_000)
        await races_db.update_meta(bot.db, state="IDLE", cooldown_until=None)
        async with s.put(
            f"{base}/api/races",
            json={"auto_enabled": False, "collect_sec": 30, "cooldown_sec": 60, "race_delay_sec": 0},
        ) as r:
            assert r.status == 200, await r.text()
            print("[OK] PUT /api/races")

        async with s.post(f"{base}/api/races/open") as r:
            assert r.status == 200, await r.text()
            print("[OK] POST /api/races/open")

        async with s.post(f"{base}/api/races/cancel") as r:
            assert r.status == 200, await r.text()
            print("[OK] POST /api/races/cancel")

        async with s.post(f"{base}/api/races/bank", json={"amount": 1000}) as r:
            assert r.status == 200, await r.text()
            print("[OK] POST /api/races/bank")

    await bot.sr.queue.clear()
    await bot.roulette.close()
    await bot.races.close()
    await bot.sr.close()
    await bot.clo.stop()
    await bot.album_web.stop()
    await bot.web.stop()
    from bot.db.migrate import get_schema_version
    from bot.db.schema import SCHEMA_VERSION

    version = await get_schema_version(bot.db.conn)
    assert version == SCHEMA_VERSION, f"schema version {version}, expected {SCHEMA_VERSION}"
    print(f"[OK] schema version {version}")
    await bot.db.close()
    for path in (tmp_db, Path(str(tmp_db) + "-wal"), Path(str(tmp_db) + "-shm")):
        if path.exists():
            path.unlink()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ensure_main_not_running()
    sys.exit(asyncio.run(main()))
