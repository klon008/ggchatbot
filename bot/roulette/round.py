"""Раунды рулетки: состояния, таймеры, ставки, спин."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import roulette as roulette_db
from bot.db.roulette import RouletteBet
from bot.economy.points import PointsStore

from . import bank, bets, wheel
from .settings import (
    BANK_RESET_AMOUNT,
    MIN_BANK_TO_START,
    ROULETTE_COLLECT_MANUAL_SEC,
    ROULETTE_COLLECT_SEC,
    ROULETTE_COOLDOWN_SEC,
    ROULETTE_SPIN_DELAY_SEC,
)

log = logging.getLogger("roulette")

SayFn = Callable[[str], Awaitable[None]]

STATE_IDLE = "IDLE"
STATE_OPEN = "OPEN"
STATE_SPIN_WAIT = "SPIN_WAIT"
STATE_SPIN = "SPIN"
STATE_COOLDOWN = "COOLDOWN"

CLOSE_BETS_MESSAGE = "Стол закрыт! Ставки больше не принимаются!"

_ACTIVE_ROUND_STATES = (STATE_OPEN, STATE_SPIN_WAIT, STATE_SPIN)


class RoundManager:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._points: Optional[PointsStore] = None
        self._say: Optional[SayFn] = None
        self._timer_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._transition_lock = asyncio.Lock()
        self._collect_sec = ROULETTE_COLLECT_SEC
        self._cooldown_sec = ROULETTE_COOLDOWN_SEC
        self._spin_delay_sec = ROULETTE_SPIN_DELAY_SEC

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    def bind_say(self, say: SayFn) -> None:
        self._say = say

    async def start(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        self._collect_sec = meta.collect_sec
        self._cooldown_sec = meta.cooldown_sec
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
                await self._begin_spin_wait()
            else:
                self._schedule_timer(meta.closes_at - now, self._on_collect_timeout)
        elif meta.state == STATE_SPIN_WAIT and meta.closes_at is not None:
            if meta.closes_at <= now:
                await self._do_spin()
            else:
                self._schedule_timer(meta.closes_at - now, self._on_spin_delay_timeout)
        elif meta.state == STATE_COOLDOWN and meta.cooldown_until is not None:
            if meta.cooldown_until <= now:
                await self._set_idle()
            else:
                self._schedule_timer(meta.cooldown_until - now, self._on_cooldown_timeout)
        elif meta.state == STATE_SPIN:
            await self._set_idle()

    async def status_snapshot(self) -> dict:
        meta = await roulette_db.get_meta(self._db)
        now = time.time()
        timer_sec = 0
        if meta.state == STATE_OPEN and meta.closes_at:
            timer_sec = max(0, int(meta.closes_at - now))
        elif meta.state == STATE_SPIN_WAIT and meta.closes_at:
            timer_sec = max(0, int(meta.closes_at - now))
        elif meta.state == STATE_COOLDOWN and meta.cooldown_until:
            timer_sec = max(0, int(meta.cooldown_until - now))

        bet_rows = []
        if meta.state in _ACTIVE_ROUND_STATES:
            for bet in await roulette_db.list_bets(self._db, meta.round_id):
                bet_rows.append({
                    "user_id": bet.user_id,
                    "user_name": bet.user_name,
                    "amount": bet.amount,
                    "bet_type": bet.bet_type,
                    "label": bets.bet_label(bet.bet_type, bet.bet_payload),
                })

        return {
            "auto_enabled": meta.auto_enabled,
            "state": meta.state,
            "bank": meta.bank,
            "round_id": meta.round_id,
            "timer_sec": timer_sec,
            "collect_sec": meta.collect_sec,
            "cooldown_sec": meta.cooldown_sec,
            "spin_delay_sec": self._spin_delay_sec,
            "bets": bet_rows,
            "last_result": meta.last_result,
        }

    async def get_auto_enabled(self) -> bool:
        meta = await roulette_db.get_meta(self._db)
        return meta.auto_enabled

    async def set_auto_enabled(self, enabled: bool) -> None:
        await roulette_db.update_meta(self._db, auto_enabled=enabled)

    async def set_timers(self, collect_sec: int, cooldown_sec: int) -> None:
        self._collect_sec = collect_sec
        self._cooldown_sec = cooldown_sec
        await roulette_db.update_meta(
            self._db,
            collect_sec=collect_sec,
            cooldown_sec=cooldown_sec,
        )

    async def get_bank(self) -> int:
        meta = await roulette_db.get_meta(self._db)
        return meta.bank

    async def top_up_bank(self, amount: int) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        return await roulette_db.add_bank(self._db, amount)

    async def reset_bank(self) -> int:
        await roulette_db.set_bank(self._db, BANK_RESET_AMOUNT)
        return BANK_RESET_AMOUNT

    async def place_bet(
        self,
        user_id: str,
        user_name: str,
        parsed: bets.ParsedBet,
    ) -> Optional[str]:
        """Принять ставку. None — успех без сообщения, str — ошибка для чата."""
        meta = await roulette_db.get_meta(self._db)
        now = time.time()

        if meta.state == STATE_COOLDOWN:
            if meta.cooldown_until and meta.cooldown_until > now:
                mins = max(1, int((meta.cooldown_until - now + 59) // 60))
                return f"Рулетка отдыхает. Подождите {mins} мин."
            await self._set_idle()
            meta = await roulette_db.get_meta(self._db)

        if meta.bank < MIN_BANK_TO_START:
            return f"Рулетка отключена: в казне менее {MIN_BANK_TO_START} баллов."

        if meta.state == STATE_IDLE:
            if not meta.auto_enabled:
                return "Стол закрыт. Ждите запуска от стримера."
            opened = await self._open_round(starter_name=user_name)
            if opened:
                await self._chat(
                    f"{user_name} запустил рулетку! У остальных есть "
                    f"{self._collect_sec} секунд, чтобы сделать свои ставки!"
                )
            meta = await roulette_db.get_meta(self._db)

        if meta.state != STATE_OPEN:
            return "Ставки сейчас не принимаются."

        if await roulette_db.has_bet(self._db, meta.round_id, user_id):
            return (
                f"{user_name}, вы уже сделали ставку в этом раунде. "
                "Дождитесь следующего спина."
            )

        if self._points is None:
            return "Рулетка временно недоступна."

        balance = await self._points.get_balance(user_id)
        if balance < parsed.amount:
            return (
                f"Недостаточно баллов. Нужно {parsed.amount}, у тебя {balance}."
            )

        await self._points.add(user_id, -parsed.amount)
        await roulette_db.add_bank(self._db, parsed.amount)
        await roulette_db.add_bet(
            self._db,
            RouletteBet(
                round_id=meta.round_id,
                user_id=str(user_id),
                user_name=user_name,
                amount=parsed.amount,
                bet_type=parsed.bet_type,
                bet_payload=parsed.bet_payload,
            ),
        )
        return None

    async def admin_open(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        if meta.auto_enabled:
            raise RuntimeError("auto_mode")
        if meta.state != STATE_IDLE:
            raise RuntimeError("not_idle")
        if meta.bank < MIN_BANK_TO_START:
            raise RuntimeError("bank_low")
        now = time.time()
        if meta.state == STATE_COOLDOWN and meta.cooldown_until and meta.cooldown_until > now:
            raise RuntimeError("cooldown")
        if meta.state == STATE_COOLDOWN:
            await self._set_idle()
        await self._open_round(starter_name=None)
        await self._chat(
            f"Стол открыт! У вас есть {self._collect_sec} секунд, чтобы сделать ставки!"
        )

    async def admin_spin(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_SPIN_WAIT):
            raise RuntimeError("not_open")
        self._cancel_timer()
        await self._do_spin()

    async def admin_cancel(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_SPIN_WAIT):
            raise RuntimeError("not_open")
        self._cancel_timer()
        bet_list = await roulette_db.list_bets(self._db, meta.round_id)
        if self._points is not None:
            for bet in bet_list:
                await self._points.add(bet.user_id, bet.amount)
        bank_refund = sum(b.amount for b in bet_list)
        if bank_refund:
            await roulette_db.add_bank(self._db, -bank_refund)
        await roulette_db.delete_bets(self._db, meta.round_id)
        await self._set_idle()
        await self._chat("Раунд отменён. Ставки возвращены.")

    async def _open_round(self, starter_name: Optional[str]) -> bool:
        meta = await roulette_db.get_meta(self._db)
        if meta.state != STATE_IDLE:
            return False
        now = time.time()
        if meta.auto_enabled:
            collect = meta.collect_sec or ROULETTE_COLLECT_SEC
        else:
            collect = meta.collect_sec or ROULETTE_COLLECT_MANUAL_SEC
        self._collect_sec = collect
        new_round_id = meta.round_id + 1
        closes_at = now + collect
        await roulette_db.update_meta(
            self._db,
            state=STATE_OPEN,
            round_id=new_round_id,
            round_opened_at=now,
            closes_at=closes_at,
            cooldown_until=None,
        )
        self._schedule_timer(collect, self._on_collect_timeout)
        return True

    async def _on_collect_timeout(self) -> None:
        await self._begin_spin_wait()

    async def _begin_spin_wait(self) -> None:
        async with self._transition_lock:
            meta = await roulette_db.get_meta(self._db)
            if meta.state != STATE_OPEN:
                return
            self._detach_timer()
            await self._chat(CLOSE_BETS_MESSAGE)
            delay = self._spin_delay_sec
            spin_at = time.time() + delay
            await roulette_db.update_meta(
                self._db,
                state=STATE_SPIN_WAIT,
                closes_at=spin_at,
            )
            if delay > 0:
                self._schedule_timer(delay, self._on_spin_delay_timeout)
            else:
                await self._do_spin_unlocked()

    async def _on_spin_delay_timeout(self) -> None:
        async with self._transition_lock:
            meta = await roulette_db.get_meta(self._db)
            if meta.state != STATE_SPIN_WAIT:
                return
            await self._do_spin_unlocked()

    async def _do_spin(self) -> None:
        async with self._transition_lock:
            await self._do_spin_unlocked()

    async def _do_spin_unlocked(self) -> None:
        self._detach_timer()
        meta = await roulette_db.get_meta(self._db)
        if meta.state not in (STATE_OPEN, STATE_SPIN_WAIT):
            return
        await roulette_db.update_meta(self._db, state=STATE_SPIN)

        result_number = wheel.spin()
        result_text = wheel.format_result(result_number)
        bet_list = await roulette_db.list_bets(self._db, meta.round_id)
        payout = bank.calculate_payouts(bet_list, result_number, meta.bank)

        if self._points is not None:
            for w in payout.winners:
                if w.actual > 0:
                    await self._points.add(w.user_id, w.actual)
            await self._points.flush()

        await roulette_db.set_bank(self._db, payout.new_bank)

        last_result = {
            "number": result_number,
            "label": result_text,
            "bankrupted": payout.bankrupted,
            "winners": [
                {
                    "user_id": w.user_id,
                    "user_name": w.user_name,
                    "ideal": w.ideal,
                    "actual": w.actual,
                }
                for w in payout.winners
            ],
        }
        await roulette_db.update_meta(self._db, last_result=last_result)

        await self._announce_spin(result_text, payout)
        await self._enter_cooldown_unlocked()

    async def _announce_spin(self, result_text: str, payout: bank.PayoutResult) -> None:
        if not payout.winners:
            await self._chat(
                f"Выпало {result_text}! Никто не угадал. Ставки остались в казне."
            )
            return

        if payout.bankrupted:
            parts = []
            for w in payout.winners:
                if w.actual > 0:
                    parts.append(f"{w.user_name} получил {w.actual} баллов")
            detail = ". ".join(parts) if parts else "Никому не досталось"
            await self._chat(
                f"Выпало {result_text.split()[0]}! Выплаты урезаны: в казне не хватило средств. "
                f"{detail}."
            )
            return

        if len(payout.winners) == 1:
            w = payout.winners[0]
            nums_only = result_text.split()[0]
            if w.ideal > w.actual * 2:
                await self._chat(
                    f"Выпало {nums_only}! {w.user_name}, вы сорвали куш "
                    f"и выиграли {w.actual} баллов!"
                )
            else:
                await self._chat(
                    f"Выпало {result_text}! {w.user_name}, вы выиграли {w.actual} баллов."
                )
            return

        parts = [
            f"{w.user_name} — {w.actual}"
            for w in payout.winners
            if w.actual > 0
        ]
        await self._chat(
            f"Выпало {result_text}! Победители: {', '.join(parts)} баллов."
        )

    async def _enter_cooldown(self) -> None:
        async with self._transition_lock:
            await self._enter_cooldown_unlocked()

    async def _enter_cooldown_unlocked(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        now = time.time()
        cooldown = meta.cooldown_sec or ROULETTE_COOLDOWN_SEC
        self._cooldown_sec = cooldown
        until = now + cooldown
        await roulette_db.update_meta(
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
        await roulette_db.update_meta(
            self._db,
            state=STATE_IDLE,
            cooldown_until=None,
            closes_at=None,
            round_opened_at=None,
        )

    async def _watchdog_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(2)
                await self._tick_scheduled_events()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("roulette watchdog failed")

    async def _tick_scheduled_events(self) -> None:
        meta = await roulette_db.get_meta(self._db)
        now = time.time()
        if meta.state == STATE_OPEN and meta.closes_at is not None and meta.closes_at <= now:
            await self._begin_spin_wait()
        elif meta.state == STATE_SPIN_WAIT and meta.closes_at is not None and meta.closes_at <= now:
            async with self._transition_lock:
                meta = await roulette_db.get_meta(self._db)
                if meta.state == STATE_SPIN_WAIT:
                    await self._do_spin_unlocked()

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
                log.exception("roulette timer failed")

        self._timer_task = asyncio.create_task(_run())

    def _detach_timer(self) -> None:
        """Сбросить ссылку на таймер, не отменяя текущую задачу (безопасно из callback)."""
        self._timer_task = None

    def _cancel_timer(self) -> None:
        task = self._timer_task
        self._timer_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _chat(self, text: str) -> None:
        if self._say is not None:
            await self._say(text)
