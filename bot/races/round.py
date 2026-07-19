"""Раунды скачек: состояния, таймеры, ставки, симуляция."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import minigames_bank
from bot.db import races as races_db
from bot.db.races import LineupEntry, RacesBet
from bot.economy.points import PointsStore
from bot.minigames.settings import BANK_RESET_AMOUNT, MIN_BANK_TO_START
from bot.princesses import princess_icon_path, princess_icon_slug

from . import bets, commentary, lineup, odds, payouts, simulate
from .bets import RACE_CMD
from .settings import (
    RACES_COLLECT_MANUAL_SEC,
    RACES_COLLECT_SEC,
    RACES_COOLDOWN_SEC,
    RACES_RACE_DELAY_SEC,
    FINISH_LINE,
    RUNNERS_COUNT,
)
from . import settings as races_settings

# Новые ключи появляются в settings.example.py; старый settings.py при update не мержится.
RACE_DISPLAY_SEC = float(getattr(races_settings, "RACE_DISPLAY_SEC", 60.0))

log = logging.getLogger("races")

SayFn = Callable[[str], Awaitable[Optional[str]]]
RemoveFn = Callable[[str], Awaitable[None]]

STATE_IDLE = "IDLE"
STATE_OPEN = "OPEN"
STATE_RACE_WAIT = "RACE_WAIT"
STATE_RACE = "RACE"
STATE_COOLDOWN = "COOLDOWN"

CLOSE_BETS_MESSAGE = "Ставки больше не принимаются!"

_ACTIVE_ROUND_STATES = (STATE_OPEN, STATE_RACE_WAIT, STATE_RACE)


def _format_payout_part(w: payouts.WinnerPayout) -> str:
    return f"{w.user_name} — {w.actual} ({w.place}-е место)"


class RoundManager:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._points: Optional[PointsStore] = None
        self._say: Optional[SayFn] = None
        self._remove: Optional[RemoveFn] = None
        self._player = None  # Optional[PlayerRoutes] — избегаем цикличного импорта
        self._live_msg_id: Optional[str] = None
        self._timer_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._transition_lock = asyncio.Lock()
        self._collect_sec = RACES_COLLECT_SEC
        self._cooldown_sec = RACES_COOLDOWN_SEC
        self._race_delay_sec = RACES_RACE_DELAY_SEC
        self._pending_race_done: Optional[asyncio.Future] = None
        self._pending_race_round_id: Optional[int] = None

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    def bind_say(self, say: SayFn) -> None:
        self._say = say

    def bind_remove(self, remove: RemoveFn) -> None:
        self._remove = remove

    def bind_obs(self, player) -> None:
        self._player = player

    def notify_race_done(self, round_id: object) -> None:
        """OBS сообщил, что анимация закончилась (победителю не доверяем)."""
        try:
            rid = int(round_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if rid != self._pending_race_round_id:
            return
        fut = self._pending_race_done
        if fut is not None and not fut.done():
            fut.set_result(True)

    async def start(self) -> None:
        meta = await races_db.get_meta(self._db)
        self._collect_sec = meta.collect_sec
        self._cooldown_sec = meta.cooldown_sec
        self._race_delay_sec = meta.race_delay_sec
        await self._recover_scheduled_state(meta)
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def close(self) -> None:
        self._cancel_timer()
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self._points is not None:
            await self._points.flush()

    async def _recover_scheduled_state(self, meta) -> None:
        now = time.time()
        if meta.state == STATE_OPEN and meta.closes_at is not None:
            if meta.closes_at <= now:
                await self._begin_race_wait()
            else:
                self._schedule_timer(meta.closes_at - now, self._on_collect_timeout)
        elif meta.state == STATE_RACE_WAIT and meta.closes_at is not None:
            if meta.closes_at <= now:
                await self._do_race()
            else:
                self._schedule_timer(meta.closes_at - now, self._on_race_delay_timeout)
        elif meta.state == STATE_COOLDOWN and meta.cooldown_until is not None:
            if meta.cooldown_until <= now:
                await self._set_idle()
            else:
                self._schedule_timer(meta.cooldown_until - now, self._on_cooldown_timeout)
        elif meta.state == STATE_RACE:
            await self._set_idle()

    async def status_snapshot(self) -> dict:
        meta = await races_db.get_meta(self._db)
        now = time.time()
        timer_sec = 0
        if meta.state == STATE_OPEN and meta.closes_at:
            timer_sec = max(0, int(meta.closes_at - now))
        elif meta.state == STATE_RACE_WAIT and meta.closes_at:
            timer_sec = max(0, int(meta.closes_at - now))
        elif meta.state == STATE_COOLDOWN and meta.cooldown_until:
            timer_sec = max(0, int(meta.cooldown_until - now))

        lineup_rows = []
        odds_map = meta.fixed_odds or {}
        bet_sums: dict[int, int] = {}
        bet_rows = []

        if meta.state in _ACTIVE_ROUND_STATES or meta.state == STATE_COOLDOWN:
            entries = await races_db.get_lineup(self._db, meta.round_id)
            for entry in entries:
                lineup_rows.append({
                    "horse_number": entry.horse_number,
                    "princess_name": entry.princess_name,
                    "icon_slug": princess_icon_slug(entry.princess_name),
                    "icon_url": princess_icon_path(entry.princess_name),
                    "coefficient": odds_map.get(str(entry.horse_number))
                    or odds_map.get(entry.horse_number),
                })

        if meta.state in _ACTIVE_ROUND_STATES:
            for bet in await races_db.list_bets(self._db, meta.round_id):
                bet_sums[bet.horse_number] = bet_sums.get(bet.horse_number, 0) + bet.amount
                bet_rows.append({
                    "user_id": bet.user_id,
                    "user_name": bet.user_name,
                    "amount": bet.amount,
                    "horse_number": bet.horse_number,
                })

        for row in lineup_rows:
            horse = row["horse_number"]
            row["bet_total"] = bet_sums.get(horse, 0)

        princess_stats_rows = []
        for stats in await races_db.list_all_princess_stats(self._db):
            races_count = stats.races_count
            wins_count = stats.wins_count
            win_rate = wins_count / races_count if races_count > 0 else 0.0
            princess_stats_rows.append({
                "princess_name": stats.princess_name,
                "icon_slug": princess_icon_slug(stats.princess_name),
                "races_count": races_count,
                "wins_count": wins_count,
                "win_rate": round(win_rate, 4),
            })

        return {
            "auto_enabled": meta.auto_enabled,
            "state": meta.state,
            "bank": await minigames_bank.get_bank(self._db),
            "round_id": meta.round_id,
            "timer_sec": timer_sec,
            "collect_sec": meta.collect_sec,
            "cooldown_sec": meta.cooldown_sec,
            "race_delay_sec": meta.race_delay_sec,
            "lineup": lineup_rows,
            "odds": odds_map,
            "bets": bet_rows,
            "race_progress": meta.race_progress,
            "finish_line": FINISH_LINE,
            "last_result": meta.last_result,
            "princess_stats": princess_stats_rows,
        }

    async def get_auto_enabled(self) -> bool:
        meta = await races_db.get_meta(self._db)
        return meta.auto_enabled

    async def set_auto_enabled(self, enabled: bool) -> None:
        await races_db.update_meta(self._db, auto_enabled=enabled)

    async def set_timers(
        self,
        collect_sec: int,
        cooldown_sec: int,
        race_delay_sec: Optional[int] = None,
    ) -> None:
        self._collect_sec = collect_sec
        self._cooldown_sec = cooldown_sec
        fields: dict = {"collect_sec": collect_sec, "cooldown_sec": cooldown_sec}
        if race_delay_sec is not None:
            self._race_delay_sec = race_delay_sec
            fields["race_delay_sec"] = race_delay_sec
        await races_db.update_meta(self._db, **fields)

    async def get_bank(self) -> int:
        return await minigames_bank.get_bank(self._db)

    async def format_odds_chat(self) -> str:
        """Текст для !забег кэфы (одна строка)."""
        meta = await races_db.get_meta(self._db)
        if meta.state not in _ACTIVE_ROUND_STATES or not meta.round_id:
            return f"Нет активного забега. Сначала откройте: {RACE_CMD}."

        entries = await races_db.get_lineup(self._db, meta.round_id)
        if not entries:
            return f"Нет активного забега. Сначала откройте: {RACE_CMD}."

        if meta.fixed_odds:
            odds_map = {int(k): float(v) for k, v in meta.fixed_odds.items()}
        else:
            bet_list = await races_db.list_bets(self._db, meta.round_id)
            odds_map = await odds.compute_odds(self._db, entries, bet_list)

        return odds.format_odds_line(entries, odds_map)

    async def top_up_bank(self, amount: int) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        return await minigames_bank.add_bank(self._db, amount)

    async def reset_bank(self) -> int:
        await minigames_bank.set_bank(self._db, BANK_RESET_AMOUNT)
        return BANK_RESET_AMOUNT

    async def open_from_chat(self, user_name: str) -> Optional[str]:
        """Открыть забег или показать состав. None — успех (сообщение уже в чате)."""
        meta = await races_db.get_meta(self._db)
        now = time.time()

        if meta.state == STATE_COOLDOWN:
            if meta.cooldown_until and meta.cooldown_until > now:
                mins = max(1, int((meta.cooldown_until - now + 59) // 60))
                return f"Забеги отдыхают. Подождите {mins} мин."
            await self._set_idle()
            meta = await races_db.get_meta(self._db)

        bank_balance = await minigames_bank.get_bank(self._db)
        if bank_balance < MIN_BANK_TO_START:
            return f"Забеги отключены: в казне менее {MIN_BANK_TO_START} баллов."

        if meta.state == STATE_OPEN:
            entries = await races_db.get_lineup(self._db, meta.round_id)
            timer_sec = 0
            if meta.closes_at:
                timer_sec = max(0, int(meta.closes_at - now))
            timer_hint = f" (осталось ~{timer_sec} сек)" if timer_sec > 0 else ""
            await self._chat(
                f"Состав: {lineup.format_lineup_short(entries)}{timer_hint}"
            )
            return None

        if meta.state != STATE_IDLE:
            return "Сейчас нельзя открыть новый забег."

        if not meta.auto_enabled:
            return "Забег закрыт. Ждите запуска от стримера."

        opened = await self._open_round(starter_name=user_name)
        if not opened:
            return "Сейчас нельзя открыть новый забег."
        entries = await races_db.get_lineup(self._db, (await races_db.get_meta(self._db)).round_id)
        await self._chat(
            f"{user_name} открыл забег! {self._collect_sec} сек — ставки для чата. "
            f"Состав: {lineup.format_lineup_short(entries)} "
            f"Узнай кэфы: !забег кэфы"
        )
        return None

    async def place_bet(
        self,
        user_id: str,
        user_name: str,
        parsed: bets.ParsedBet,
    ) -> Optional[str]:
        meta = await races_db.get_meta(self._db)
        now = time.time()

        if meta.state == STATE_COOLDOWN:
            if meta.cooldown_until and meta.cooldown_until > now:
                mins = max(1, int((meta.cooldown_until - now + 59) // 60))
                return f"Забеги отдыхают. Подождите {mins} мин."
            await self._set_idle()
            meta = await races_db.get_meta(self._db)

        bank_balance = await minigames_bank.get_bank(self._db)
        if bank_balance < MIN_BANK_TO_START:
            return f"Забеги отключены: в казне менее {MIN_BANK_TO_START} баллов."

        if meta.state == STATE_IDLE:
            return f"Сначала откройте забег командой {RACE_CMD} (или дождитесь стримера)."

        if meta.state != STATE_OPEN:
            return "Ставки сейчас не принимаются."

        current_lineup = await races_db.get_lineup(self._db, meta.round_id)
        horse_numbers = {e.horse_number for e in current_lineup}
        if parsed.horse_number not in horse_numbers:
            return f"Номер лошади должен быть от 1 до {RUNNERS_COUNT}."

        if await races_db.has_bet(self._db, meta.round_id, user_id):
            return "Вы уже сделали ставку в этом забеге. Дождитесь следующего старта."

        if self._points is None:
            return "Забеги временно недоступны."

        balance = await self._points.get_balance(user_id)
        if balance < parsed.amount:
            return f"Недостаточно баллов. Нужно {parsed.amount}, у тебя {balance}."

        await self._points.add(user_id, -parsed.amount)
        await minigames_bank.add_bank(self._db, parsed.amount)
        await races_db.add_bet(
            self._db,
            RacesBet(
                round_id=meta.round_id,
                user_id=str(user_id),
                user_name=user_name,
                amount=parsed.amount,
                horse_number=parsed.horse_number,
            ),
        )
        return None

    async def admin_open(self) -> None:
        meta = await races_db.get_meta(self._db)
        if meta.auto_enabled:
            raise RuntimeError("auto_mode")
        if meta.state != STATE_IDLE:
            raise RuntimeError("not_idle")
        bank_balance = await minigames_bank.get_bank(self._db)
        if bank_balance < MIN_BANK_TO_START:
            raise RuntimeError("bank_low")
        now = time.time()
        if meta.state == STATE_COOLDOWN and meta.cooldown_until and meta.cooldown_until > now:
            raise RuntimeError("cooldown")
        if meta.state == STATE_COOLDOWN:
            await self._set_idle()
        await self._open_round(starter_name=None)
        entries = await races_db.get_lineup(self._db, (await races_db.get_meta(self._db)).round_id)
        await self._chat(
            f"Забег открыт! {self._collect_sec} сек — ставки для чата. "
            f"Состав: {lineup.format_lineup_short(entries)}"
        )

    async def admin_start(self) -> None:
        meta = await races_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_RACE_WAIT):
            raise RuntimeError("not_open")
        self._cancel_timer()
        async with self._transition_lock:
            meta = await races_db.get_meta(self._db)
            if meta.state == STATE_OPEN:
                await self._close_bets_for_race_unlocked()
            meta = await races_db.get_meta(self._db)
            if meta.state in (STATE_OPEN, STATE_RACE_WAIT):
                await self._do_race_unlocked()

    async def _close_bets_for_race_unlocked(self) -> None:
        meta = await races_db.get_meta(self._db)
        if meta.state != STATE_OPEN:
            return
        await self._chat(CLOSE_BETS_MESSAGE)
        entries = await races_db.get_lineup(self._db, meta.round_id)
        bet_list = await races_db.list_bets(self._db, meta.round_id)
        odds_map = await odds.compute_odds(self._db, entries, bet_list)
        odds_serializable = {str(k): round(v, 2) for k, v in odds_map.items()}
        await races_db.update_meta(
            self._db,
            state=STATE_RACE_WAIT,
            closes_at=time.time(),
            fixed_odds=odds_serializable,
        )

    async def admin_cancel(self) -> None:
        meta = await races_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_RACE_WAIT):
            raise RuntimeError("not_open")
        self._cancel_timer()
        bet_list = await races_db.list_bets(self._db, meta.round_id)
        if self._points is not None:
            for bet in bet_list:
                await self._points.add(bet.user_id, bet.amount)
        bank_refund = sum(b.amount for b in bet_list)
        if bank_refund:
            await minigames_bank.add_bank(self._db, -bank_refund)
        await races_db.delete_bets(self._db, meta.round_id)
        await self._set_idle()
        await self._chat("Забег отменён. Ставки возвращены.")

    async def _open_round(self, starter_name: Optional[str]) -> bool:
        meta = await races_db.get_meta(self._db)
        if meta.state != STATE_IDLE:
            return False
        now = time.time()
        if meta.auto_enabled:
            collect = meta.collect_sec or RACES_COLLECT_SEC
        else:
            collect = meta.collect_sec or RACES_COLLECT_MANUAL_SEC
        self._collect_sec = collect
        new_round_id = meta.round_id + 1
        closes_at = now + collect
        entries = lineup.pick_lineup()
        await races_db.save_lineup(self._db, new_round_id, entries)
        await races_db.update_meta(
            self._db,
            state=STATE_OPEN,
            round_id=new_round_id,
            round_opened_at=now,
            closes_at=closes_at,
            cooldown_until=None,
            fixed_odds=None,
            race_progress=None,
        )
        self._schedule_timer(collect, self._on_collect_timeout)
        return True

    async def _on_collect_timeout(self) -> None:
        await self._begin_race_wait()

    async def _begin_race_wait(self) -> None:
        async with self._transition_lock:
            meta = await races_db.get_meta(self._db)
            if meta.state != STATE_OPEN:
                return
            self._detach_timer()
            await self._close_bets_for_race_unlocked()
            delay = self._race_delay_sec
            if delay > 0:
                race_at = time.time() + delay
                await races_db.update_meta(self._db, closes_at=race_at)
                self._schedule_timer(delay, self._on_race_delay_timeout)
            else:
                await self._do_race_unlocked()

    async def _on_race_delay_timeout(self) -> None:
        async with self._transition_lock:
            meta = await races_db.get_meta(self._db)
            if meta.state != STATE_RACE_WAIT:
                return
            await self._do_race_unlocked()

    async def _do_race(self) -> None:
        async with self._transition_lock:
            await self._do_race_unlocked()

    async def _do_race_unlocked(self) -> None:
        self._detach_timer()
        meta = await races_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_RACE_WAIT):
            return

        round_id = meta.round_id
        await races_db.update_meta(
            self._db,
            state=STATE_RACE,
            race_progress={"playing": True, "round_id": round_id},
        )

        entries = await races_db.get_lineup(self._db, round_id)
        bet_list = await races_db.list_bets(self._db, round_id)
        odds_map_raw = meta.fixed_odds
        if not odds_map_raw:
            odds_map_raw = await odds.compute_odds(self._db, entries, bet_list)
            odds_map_raw = {str(k): round(v, 2) for k, v in odds_map_raw.items()}
        odds_map = {int(k): float(v) for k, v in odds_map_raw.items()}

        result = simulate.simulate_race(entries)
        name_by_horse = {e.horse_number: e.princess_name for e in entries}

        display_sec = float(RACE_DISPLAY_SEC)

        script = simulate.build_obs_script(
            result,
            entries,
            display_sec=display_sec,
            finish_line=FINISH_LINE,
        )
        display_sec = float(script["durationSec"])
        script["roundId"] = round_id
        script["lineup"] = [
            {
                "horse_number": e.horse_number,
                "princess_name": e.princess_name,
                "icon_slug": princess_icon_slug(e.princess_name),
                "icon_url": princess_icon_path(e.princess_name),
            }
            for e in entries
        ]

        await self._chat("Старт! Погнали!")

        loop = asyncio.get_running_loop()
        self._pending_race_round_id = round_id
        self._pending_race_done = loop.create_future()

        has_obs = bool(self._player and self._player.has_races_clients)
        if has_obs:
            await self._player.broadcast_races({"action": "race_start", **script})
            timeout = max(1.0, display_sec + 16.0)  # +countdown 10..1-Старт! и запас

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._pending_race_done), timeout=timeout
                )
            except asyncio.TimeoutError:
                log.info("Races: таймаут анимации (%.1fs), продолжаем выплаты", timeout)
        else:
            log.warning(
                "Races OBS не подключён — пауза %.0fs без анимации (round=%s)",
                display_sec,
                round_id,
            )
            await asyncio.sleep(display_sec)

        self._pending_race_done = None
        self._pending_race_round_id = None

        bank_balance = await minigames_bank.get_bank(self._db)
        payout = payouts.calculate_payouts(
            bet_list,
            result.finish_order,
            odds_map,
            bank_balance,
        )

        if self._points is not None:
            for w in payout.winners:
                if w.actual > 0:
                    await self._points.add(w.user_id, w.actual)
            await self._points.flush()

        await minigames_bank.set_bank(self._db, payout.new_bank)
        princess_names = [e.princess_name for e in entries]
        await races_db.record_race_result(self._db, princess_names, result.winner_name)

        last_result = {
            "winner_horse": result.winner_horse,
            "winner_name": result.winner_name,
            "finish_order": result.finish_order,
            "bankrupted": payout.bankrupted,
            "odds": odds_map_raw,
            "winners": [
                {
                    "user_id": w.user_id,
                    "user_name": w.user_name,
                    "horse_number": w.horse_number,
                    "place": w.place,
                    "ideal": w.ideal,
                    "actual": w.actual,
                }
                for w in payout.winners
            ],
        }
        await races_db.update_meta(self._db, last_result=last_result, race_progress=None)
        await self._clear_live_chat()
        await self._announce_finish(result, payout, odds_map, name_by_horse)
        await self._enter_cooldown_unlocked()

    async def _announce_finish(
        self,
        result: simulate.RaceResult,
        payout: payouts.PayoutResult,
        odds_map: dict[int, float],
        name_by_horse: dict[int, str],
    ) -> None:
        coeff = odds_map.get(result.winner_horse, 0)
        header = commentary.format_finish_header(
            result.winner_horse,
            result.winner_name,
            coeff,
            result.finish_order,
            name_by_horse,
        )
        if not payout.winners:
            await self._chat(f"{header} Никто не угадал. Ставки остались в казне.")
            return
        parts = [
            _format_payout_part(w)
            for w in payout.winners
            if w.actual > 0
        ]
        if payout.bankrupted:
            await self._chat(
                f"{header} Выплаты урезаны: в казне не хватило средств. "
                f"Выплаты: {', '.join(parts)}."
            )
            return
        if len(parts) == 1:
            await self._chat(f"{header} {parts[0]}.")
            return
        await self._chat(f"{header} Выплаты: {', '.join(parts)}.")

    async def _enter_cooldown_unlocked(self) -> None:
        meta = await races_db.get_meta(self._db)
        now = time.time()
        cooldown = meta.cooldown_sec or RACES_COOLDOWN_SEC
        self._cooldown_sec = cooldown
        until = now + cooldown
        await races_db.update_meta(
            self._db,
            state=STATE_COOLDOWN,
            cooldown_until=until,
            closes_at=None,
            round_opened_at=None,
        )
        self._schedule_timer(cooldown, self._on_cooldown_timeout)

    async def _on_cooldown_timeout(self) -> None:
        await self._set_idle()

    async def _set_idle(self) -> None:
        self._cancel_timer()
        await races_db.update_meta(
            self._db,
            state=STATE_IDLE,
            cooldown_until=None,
            closes_at=None,
            round_opened_at=None,
            race_progress=None,
        )

    async def _watchdog_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(2)
                await self._tick_scheduled_events()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("races watchdog failed")

    async def _tick_scheduled_events(self) -> None:
        meta = await races_db.get_meta(self._db)
        now = time.time()
        if meta.state == STATE_OPEN and meta.closes_at is not None and meta.closes_at <= now:
            await self._begin_race_wait()
        elif meta.state == STATE_RACE_WAIT and meta.closes_at is not None and meta.closes_at <= now:
            async with self._transition_lock:
                meta = await races_db.get_meta(self._db)
                if meta.state == STATE_RACE_WAIT:
                    await self._do_race_unlocked()

    def _schedule_timer(self, delay_sec: float, callback) -> None:
        self._cancel_timer()
        delay_sec = max(0.0, delay_sec)

        async def _run():
            try:
                if delay_sec > 0:
                    await asyncio.sleep(delay_sec)
                await callback()
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("races timer failed")

        self._timer_task = asyncio.create_task(_run())

    def _detach_timer(self) -> None:
        self._timer_task = None

    def _cancel_timer(self) -> None:
        task = self._timer_task
        self._timer_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _chat(self, text: str) -> None:
        if self._say is not None:
            await self._say(text)

    async def _chat_live(self, text: str) -> None:
        """Отправить комментарий, удалив предыдущий live-месседж."""
        await self._clear_live_chat()
        if self._say is not None:
            self._live_msg_id = await self._say(text)
        else:
            log.info("races (no reply): %s", text)

    async def _clear_live_chat(self) -> None:
        msg_id = self._live_msg_id
        self._live_msg_id = None
        if msg_id and self._remove is not None:
            try:
                await self._remove(msg_id)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось удалить live-сообщение забега %s", msg_id)
