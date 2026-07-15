"""Раунды опросов: OPEN → LOCKED → RESOLVED, ставки peer-pool."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import poll as poll_db
from bot.db.poll import PollBet
from bot.economy.points import PointsStore

from . import payouts
from .settings import (
    POLL_CMD,
    POLL_DEFAULT_COLLECT_SEC,
    POLL_MAX_COLLECT_SEC,
    POLL_MAX_OPTIONS,
    POLL_MIN_COLLECT_SEC,
    POLL_MIN_OPTIONS,
    POLL_MIN_STAKE,
    POLL_RESOLVED_DISPLAY_SEC,
)

log = logging.getLogger("polls")

SayFn = Callable[[str], Awaitable[None]]

STATE_IDLE = "IDLE"
STATE_OPEN = "OPEN"
STATE_LOCKED = "LOCKED"
STATE_RESOLVED = "RESOLVED"

CLOSE_BETS_MESSAGE = "Приём ставок закрыт! Ждём результат от стримера."


class RoundManager:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._points: Optional[PointsStore] = None
        self._say: Optional[SayFn] = None
        self._timer_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._transition_lock = asyncio.Lock()

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    def bind_say(self, say: SayFn) -> None:
        self._say = say

    async def start(self) -> None:
        meta = await poll_db.get_meta(self._db)
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
                await self._lock_bets(announce=True)
            else:
                self._schedule_timer(meta.closes_at - now, self._on_collect_timeout)
        elif meta.state == STATE_RESOLVED and meta.closes_at is not None:
            if meta.closes_at <= now:
                await self._clear_to_idle()
            else:
                self._schedule_timer(meta.closes_at - now, self._on_resolved_timeout)

    async def _watchdog_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                await self._watchdog_tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("polls watchdog error")

    async def _watchdog_tick(self) -> None:
        meta = await poll_db.get_meta(self._db)
        now = time.time()
        if meta.state == STATE_OPEN and meta.closes_at is not None and meta.closes_at <= now:
            await self._lock_bets(announce=True)
        elif (
            meta.state == STATE_RESOLVED
            and meta.closes_at is not None
            and meta.closes_at <= now
        ):
            await self._clear_to_idle()

    def _cancel_timer(self) -> None:
        if self._timer_task is not None:
            self._timer_task.cancel()
            self._timer_task = None

    def _schedule_timer(self, delay: float, callback) -> None:
        self._cancel_timer()

        async def _runner() -> None:
            try:
                await asyncio.sleep(max(0.0, delay))
                await callback()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("polls timer callback error")

        self._timer_task = asyncio.create_task(_runner())

    async def _chat(self, text: str) -> None:
        if self._say is not None:
            await self._say(text)
        else:
            log.info("polls (no say): %s", text)

    async def _on_collect_timeout(self) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_OPEN:
                return
            await self._lock_bets_unlocked(announce=True)

    async def _on_resolved_timeout(self) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_RESOLVED:
                return
            await self._clear_to_idle_unlocked()

    def _option_stats(self, options: list[str], bet_list: list[PollBet]) -> list[dict]:
        totals = [0] * len(options)
        counts = [0] * len(options)
        for bet in bet_list:
            if 0 <= bet.option_index < len(options):
                totals[bet.option_index] += bet.amount
                counts[bet.option_index] += 1
        total_pool = sum(totals)
        rows = []
        for i, label in enumerate(options):
            rows.append({
                "index": i,
                "label": label,
                "total": totals[i],
                "bets_count": counts[i],
                "coefficient": round(payouts.option_coefficient(totals[i], total_pool), 2),
            })
        return rows

    async def status_snapshot(self) -> dict:
        meta = await poll_db.get_meta(self._db)
        now = time.time()
        timer_sec = 0
        if meta.state in (STATE_OPEN, STATE_RESOLVED) and meta.closes_at:
            timer_sec = max(0, int(meta.closes_at - now))

        bet_list: list[PollBet] = []
        if meta.state in (STATE_OPEN, STATE_LOCKED) and meta.round_id > 0:
            bet_list = await poll_db.list_bets(self._db, meta.round_id)

        if meta.state in (STATE_OPEN, STATE_LOCKED):
            option_rows = self._option_stats(meta.options, bet_list)
            title = meta.title
        elif meta.state == STATE_RESOLVED and meta.last_result:
            option_rows = meta.last_result.get("options_stats", [])
            title = meta.last_result.get("title", "") or ""
        elif meta.last_result:
            option_rows = meta.last_result.get("options_stats", [])
            title = meta.last_result.get("title", "") or ""
        else:
            option_rows = []
            title = ""

        bet_rows = [
            {
                "user_id": b.user_id,
                "user_name": b.user_name,
                "amount": b.amount,
                "option_index": b.option_index,
                "option_label": (
                    meta.options[b.option_index]
                    if 0 <= b.option_index < len(meta.options)
                    else str(b.option_index + 1)
                ),
            }
            for b in bet_list
        ]

        winning_option = meta.winning_option
        if winning_option is None and meta.last_result:
            winning_option = meta.last_result.get("winning_option")

        return {
            "state": meta.state,
            "round_id": meta.round_id,
            "title": title if title else meta.title,
            "options": option_rows,
            "timer_sec": timer_sec,
            "collect_sec": meta.collect_sec,
            "winning_option": winning_option,
            "bets": bet_rows,
            "total_pool": (
                sum(b.amount for b in bet_list)
                if bet_list
                else (meta.last_result or {}).get("total_pool", 0)
            ),
            "min_stake": POLL_MIN_STAKE,
            "last_result": meta.last_result,
        }

    async def place_bet(
        self,
        user_id: str,
        user_name: str,
        amount: int,
        option_index: int,
    ) -> Optional[str]:
        meta = await poll_db.get_meta(self._db)
        if meta.state == STATE_IDLE:
            return "Сейчас нет активного опроса."
        if meta.state == STATE_LOCKED:
            return "Приём ставок закрыт."
        if meta.state == STATE_RESOLVED:
            return "Опрос уже завершён."
        if meta.state != STATE_OPEN:
            return "Ставки сейчас не принимаются."

        if amount < POLL_MIN_STAKE:
            return f"Минимальная ставка: {POLL_MIN_STAKE}."
        if option_index < 0 or option_index >= len(meta.options):
            return f"Вариант должен быть от 1 до {len(meta.options)}."

        if self._points is None:
            return "Опросы временно недоступны."

        existing = await poll_db.get_bet(self._db, meta.round_id, user_id)
        if existing is not None and existing.option_index != option_index:
            label = meta.options[existing.option_index]
            return (
                f"Ты уже поставил на «{label}». "
                "Можно только добавить сумму на тот же вариант."
            )

        balance = await self._points.get_balance(user_id)
        if balance < amount:
            return f"Недостаточно баллов. Нужно {amount}, у тебя {balance}."

        await self._points.add(user_id, -amount)
        await self._points.flush_pending()

        if existing is None:
            await poll_db.add_bet(
                self._db,
                PollBet(
                    round_id=meta.round_id,
                    user_id=str(user_id),
                    user_name=user_name,
                    amount=amount,
                    option_index=option_index,
                ),
            )
        else:
            await poll_db.add_to_bet(
                self._db, meta.round_id, user_id, amount, user_name
            )

        return None

    async def admin_create(
        self,
        title: str,
        options: list[str],
        collect_sec: int,
    ) -> None:
        title = (title or "").strip()
        if not title:
            raise RuntimeError("empty_title")
        cleaned = [str(o).strip() for o in options if str(o).strip()]
        if len(cleaned) < POLL_MIN_OPTIONS:
            raise RuntimeError("too_few_options")
        if len(cleaned) > POLL_MAX_OPTIONS:
            raise RuntimeError("too_many_options")
        if collect_sec < POLL_MIN_COLLECT_SEC or collect_sec > POLL_MAX_COLLECT_SEC:
            raise RuntimeError("bad_collect_sec")

        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_IDLE:
                raise RuntimeError("not_idle")

            now = time.time()
            new_round_id = meta.round_id + 1
            closes_at = now + collect_sec
            await poll_db.update_meta(
                self._db,
                state=STATE_OPEN,
                round_id=new_round_id,
                title=title,
                options=cleaned,
                round_opened_at=now,
                closes_at=closes_at,
                collect_sec=collect_sec,
                winning_option=None,
                last_result=None,
            )
            self._schedule_timer(collect_sec, self._on_collect_timeout)

        mins = max(1, collect_sec // 60)
        variants = " | ".join(f"{i + 1}) {o}" for i, o in enumerate(cleaned))
        await self._chat(
            f"Опрос открыт ({mins} мин)! {title} — {variants}. "
            f"Ставка: {POLL_CMD} <сумма> <номер> (мин. {POLL_MIN_STAKE})"
        )

    async def admin_lock(self) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_OPEN:
                raise RuntimeError("not_open")
            await self._lock_bets_unlocked(announce=True)

    async def _lock_bets(self, announce: bool) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_OPEN:
                return
            await self._lock_bets_unlocked(announce=announce)

    async def _lock_bets_unlocked(self, announce: bool) -> None:
        self._cancel_timer()
        await poll_db.update_meta(
            self._db,
            state=STATE_LOCKED,
            closes_at=None,
        )
        if announce:
            await self._chat(CLOSE_BETS_MESSAGE)

    async def admin_resolve(self, option_index: int) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state != STATE_LOCKED:
                raise RuntimeError("not_locked")
            if option_index < 0 or option_index >= len(meta.options):
                raise RuntimeError("bad_option")

            bet_list = await poll_db.list_bets(self._db, meta.round_id)
            winners_on_option = [
                b for b in bet_list if b.option_index == option_index
            ]
            if bet_list and not winners_on_option:
                raise RuntimeError("no_winners")

            result = payouts.calculate_payouts(bet_list, option_index)
            if self._points is not None:
                for w in result.winners:
                    await self._points.add(w.user_id, w.payout)
                await self._points.flush_pending()

            option_stats = self._option_stats(meta.options, bet_list)
            last_result = {
                "title": meta.title,
                "options": meta.options,
                "options_stats": option_stats,
                "winning_option": option_index,
                "winning_label": meta.options[option_index],
                "total_pool": result.total_pool,
                "winners_pool": result.winners_pool,
                "losers_pool": result.losers_pool,
                "winners": [
                    {
                        "user_id": w.user_id,
                        "user_name": w.user_name,
                        "stake": w.stake,
                        "payout": w.payout,
                    }
                    for w in result.winners
                ],
            }
            now = time.time()
            await poll_db.delete_bets(self._db, meta.round_id)
            await poll_db.update_meta(
                self._db,
                state=STATE_RESOLVED,
                winning_option=option_index,
                last_result=last_result,
                closes_at=now + POLL_RESOLVED_DISPLAY_SEC,
                title="",
                options=[],
            )
            self._schedule_timer(POLL_RESOLVED_DISPLAY_SEC, self._on_resolved_timeout)

        await self._announce_resolve(last_result)

    async def _announce_resolve(self, last_result: dict) -> None:
        label = last_result["winning_label"]
        pool = last_result["total_pool"]
        winners = last_result.get("winners") or []
        if not winners:
            await self._chat(
                f"Опрос завершён! Победил «{label}». "
                + ("Ставок не было." if pool == 0 else f"Банк {pool}.")
            )
            return

        top = sorted(winners, key=lambda w: -w["payout"])[:5]
        parts = [f"{w['user_name']} +{w['payout']}" for w in top]
        suffix = "…" if len(winners) > 5 else ""
        await self._chat(
            f"Опрос завершён! Победил «{label}». Банк {pool}. "
            f"Выплаты: {', '.join(parts)}{suffix}"
        )

    async def admin_cancel(self) -> None:
        async with self._transition_lock:
            meta = await poll_db.get_meta(self._db)
            if meta.state not in (STATE_OPEN, STATE_LOCKED):
                raise RuntimeError("not_active")
            self._cancel_timer()
            bet_list = await poll_db.list_bets(self._db, meta.round_id)
            if self._points is not None:
                for bet in bet_list:
                    await self._points.add(bet.user_id, bet.amount)
                await self._points.flush_pending()
            await poll_db.delete_bets(self._db, meta.round_id)
            await self._clear_to_idle_unlocked()
        await self._chat("Опрос отменён. Все ставки возвращены.")

    async def _clear_to_idle(self) -> None:
        async with self._transition_lock:
            await self._clear_to_idle_unlocked()

    async def _clear_to_idle_unlocked(self) -> None:
        self._cancel_timer()
        meta = await poll_db.get_meta(self._db)
        # keep last_result for overlay/history, clear active fields
        await poll_db.update_meta(
            self._db,
            state=STATE_IDLE,
            title="",
            options=[],
            round_opened_at=None,
            closes_at=None,
            winning_option=None,
            # last_result preserved
            collect_sec=meta.collect_sec or POLL_DEFAULT_COLLECT_SEC,
        )

    def format_status_chat(self, snap: dict) -> str:
        state = snap["state"]
        if state == STATE_IDLE:
            return "Сейчас нет активного опроса."
        title = snap.get("title") or "Опрос"
        opts = snap.get("options") or []
        parts = []
        for o in opts:
            parts.append(
                f"{o['index'] + 1}) {o['label']} — {o['total']} "
                f"(x{o['coefficient']:.2f})"
            )
        timer = ""
        if state == STATE_OPEN and snap.get("timer_sec"):
            timer = f" До закрытия: {snap['timer_sec']} сек."
        elif state == STATE_LOCKED:
            timer = " Приём закрыт, ждём результат."
        elif state == STATE_RESOLVED:
            lr = snap.get("last_result") or {}
            win = lr.get("winning_label", "?")
            return f"Опрос завершён. Победил «{win}»."
        pool = snap.get("total_pool", 0)
        return (
            f"{title} [банк {pool}]. {'; '.join(parts)}.{timer} "
            f"Ставка: {POLL_CMD} <сумма> <номер>"
        )
