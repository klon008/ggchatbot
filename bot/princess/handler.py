"""Обработчик princess-команд и пассивного дохода в чате."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional

from bot.goodgame import ChatMessage

from bot.db import Database

from .economy import (
    calculate_princess_amount,
    get_daily_bonus,
    is_steal_allowed,
    now_msk,
    pluralize_princess,
    prison_chance_for_amount,
    update_chance,
)
from .prison import PrisonManager
from .settings import (
    DICE_COOLDOWN_SEC,
    DICE_COST,
    DICE_CRITICAL_FAIL,
    DICE_CRITICAL_FAIL_PENALTY,
    DICE_CRITICAL_SUCCESS,
    DICE_CRITICAL_SUCCESS_REWARD,
    DICE_ROLL_MAX,
    DICE_ROLL_MIN,
    MESSAGE_POINTS,
    PASSIVE_INCOME_INTERVAL_SEC,
    PASSIVE_INCOME_PER_MIN,
    PRISON_DURATION_SEC,
    STEAL_AMOUNT_MAX,
    STEAL_AMOUNT_MIN,
    STEAL_COOLDOWN_SEC,
    STEAL_MIN_VIEWERS,
    STEAL_ROLL_MAX,
    VICTIM_MIN_BALANCE,
)
from .storage import DailyStore, DiceCooldownStore, PointsStore, StealStore

log = logging.getLogger("princess")

ReplyFn = Callable[[str, str], Awaitable[None]]  # user_name, text (без префикса имени)
ViewersFetchFn = Callable[[], Awaitable[list[dict]]]

DISNEY_PRINCESSES = [
    "Белоснежка", "Аврора", "Золушка", "Мулан", "Рапунцель",
    "Тиана", "Покахонтас", "Ариэль", "Жасмин", "Эльза",
    "Анна", "Моана", "Мерида", "Бэлль", "Ванилопа", "Алиса",
    "Эсмеральда", "Кида", "Мегара", "Райя", "Джейн Портер",
]

POOR_VICTIM_MESSAGES = [
    "У {name} недостаточно крупный кошелёк. Пусть сначала накопит немного",
    "{name} слишком бедный. Нет смысла красть",
    "{name} доедает последний *** без соли. Лучше укради у кого-нибудь еще",
    "У {name} менее 18к принцесс. Не трогай его",
    "Хочешь украсть у {name}? Не надо, там слишком мало богатств",
    "Пытаешься красть у нищего {name}? Знаешь, я был о тебе лучшего мнения",
    "Я просканировал кошелек {name}. Там пока что нет 18к принцесс",
    "У жертвы должно быть не менее 18к принцесс. У {name} нет столько",
]


class PrincessHandler:
    """Игровая экономика принцесс — команды, пассивный доход, тюрьма."""

    def __init__(self, db: Database, admin_user_id: str, bot_user_id: str = "") -> None:
        self._db = db
        self.admin_user_id = str(admin_user_id).strip()
        self._bot_user_id = str(bot_user_id).strip()
        self.points = PointsStore(db)
        self.steal = StealStore(db)
        self.daily = DailyStore(db)
        self.prison = PrisonManager(db)
        self.dice_cooldowns = DiceCooldownStore(db)
        self._viewers: dict[str, dict] = {}
        self._tick_task: Optional[asyncio.Task] = None
        self._reply: Optional[ReplyFn] = None
        self._fetch_viewers: Optional[ViewersFetchFn] = None

    async def start(self) -> None:
        await self.points.load()
        await self.steal.load()
        await self.daily.load()
        await self.daily.normalize()
        self._tick_task = asyncio.create_task(self._passive_income_loop())
        log.info("Princess-модуль запущен.")

    async def close(self) -> None:
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_viewers_fetch(self, fetch: ViewersFetchFn) -> None:
        self._fetch_viewers = fetch

    def sync_viewers(self, users: list[dict]) -> None:
        """Заменить список зрителей данными из get_users_list2."""
        now = time.time()
        new_viewers: dict[str, dict] = {}
        for user in users:
            uid = str(user.get("id", ""))
            if not uid or uid == "0":
                continue
            if self._bot_user_id and uid == self._bot_user_id:
                continue
            new_viewers[uid] = {
                "user_name": str(user.get("name", "")),
                "last_active": self._viewers.get(uid, {}).get("last_active", now),
            }
        self._viewers = new_viewers

    async def _refresh_viewers(self) -> bool:
        if self._fetch_viewers is None:
            log.warning("fetch_viewers не привязан — пропуск синхронизации зрителей.")
            return False
        try:
            users = await self._fetch_viewers()
        except Exception:  # noqa: BLE001
            log.warning("Не удалось получить список зрителей.", exc_info=True)
            return False
        self.sync_viewers(users)
        log.debug("Список зрителей обновлён: %d человек.", len(self._viewers))
        return True

    async def handle_message(self, msg: ChatMessage) -> bool:
        """Обработать сообщение. True — princess-команда обработана (SR не нужен)."""
        text = msg.text.strip()
        user_id = msg.user_id
        user_name = msg.user_name

        cmd = text.split(maxsplit=1)[0].lower() if text.startswith("!") else ""

        await self.points.touch_name_if_new(user_id, user_name)

        if await self.prison.is_in_prison(user_id):
            if cmd == "!срок":
                await self._say(user_name, await self.prison.format_srok(user_id))
            return True

        await self.points.add(user_id, MESSAGE_POINTS)

        if not text.startswith("!"):
            return False

        handlers = {
            "!срок": self._cmd_srok,
            "!кража": self._cmd_steal,
            "!нейро": self._cmd_neuro,
            "!звук": self._cmd_sound,
            "!дайс": self._cmd_dice,
            "!дисней": self._cmd_disney,
            "!баллы": self._cmd_points,
            "!карман": self._cmd_pocket,
            "!коллекция": self._cmd_collection,
            "!дейлик": self._cmd_daily,
        }

        if cmd in handlers:
            await handlers[cmd](msg)
            return True

        if cmd in ("!списать", "!начислить"):
            await self._cmd_admin_points(msg)
            return True

        return False

    # --- пассивный доход -------------------------------------------------
    async def _passive_income_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(PASSIVE_INCOME_INTERVAL_SEC)
                if not await self._refresh_viewers():
                    continue
                for uid in list(self._viewers.keys()):
                    if await self.prison.is_in_prison(uid):
                        continue
                    await self.points.add(uid, PASSIVE_INCOME_PER_MIN)
        except asyncio.CancelledError:
            raise

    # --- команды ---------------------------------------------------------
    async def _cmd_srok(self, msg: ChatMessage) -> None:
        await self._say(msg.user_name, await self.prison.format_srok(msg.user_id))

    async def _cmd_points(self, msg: ChatMessage) -> None:
        count = await self.points.get_balance(msg.user_id)
        await self._say(msg.user_name, f"У тебя: {count} {pluralize_princess(count)}")

    async def _cmd_neuro(self, msg: ChatMessage) -> None:
        await self._say(
            msg.user_name,
            "Здесь стример создаёт своих принцесс: "
            "https://shedevrum.ai/@dartval?share=444jmjdeffe2b8k8w14vq8c350",
        )

    async def _cmd_sound(self, msg: ChatMessage) -> None:
        await self._say(
            msg.user_name,
            "Доступные звуковые команды: нифига, даблин, незнаю, поновой, сколько, "
            "смех, прыгай, жаль, тяжело, скандал, окэй, беги, верю, протест, "
            "видно, хорошо, супер, ашалеть, кря",
        )

    async def _cmd_disney(self, msg: ChatMessage) -> None:
        princess = random.choice(DISNEY_PRINCESSES)
        await self._say(
            msg.user_name,
            f"Какая принцесса Диснея ты сегодня? Сегодня ты - {princess}!",
        )

    async def _cmd_collection(self, msg: ChatMessage) -> None:
        await self._say(msg.user_name, "Обзор коллекции стримера: https://youtu.be/UBJuIAMbW_I")

    async def _cmd_pocket(self, msg: ChatMessage) -> None:
        async with self.steal.mutate_info(msg.user_id) as data:
            update_chance(data)
            attempts = data["attempts"]
            successes = data["success"]
            total_stolen = data.get("stolen_total", 0)
            chance = data["chance"]
            times_in_jail = data.get("times_in_jail", 0)

        await self._say(
            msg.user_name,
            "твоя статистика:\n"
            f"Попыток: {attempts}\n"
            f"Успехов: {successes}\n"
            f"Всего украдено принцесс: {total_stolen}\n"
            f"Количество отсидок: {times_in_jail}\n"
            f"Текущий шанс кражи: {chance}%",
        )

    async def _cmd_daily(self, msg: ChatMessage) -> None:
        if msg.text.strip().lower() != "!дейлик":
            return

        today = now_msk()
        today_str = today.strftime("%Y-%m-%d")
        current_month = today.strftime("%Y-%m")
        uid = msg.user_id

        async with self.daily.mutate() as data:
            if data.get("current_month") != current_month:
                data["current_month"] = current_month
                data["user_progress"] = {}

            if today_str in data and uid in data[today_str]:
                await self._say(msg.user_name, "Ты уже получил(а) ежедневный бонус сегодня!")
                return

            counter = data["user_progress"].get(uid, 0) + 1
            bonus = get_daily_bonus(counter)
            data["user_progress"][uid] = counter
            data.setdefault(today_str, [])
            if uid not in data[today_str]:
                data[today_str].append(uid)

        await self.points.add(uid, bonus)
        await self._say(msg.user_name, f"Ты получил(а) ежедневный бонус {bonus} принцесс!")

    async def _cmd_dice(self, msg: ChatMessage) -> None:
        uid = msg.user_id
        now = time.time()
        last = await self.dice_cooldowns.get_last(uid)
        if now - last < DICE_COOLDOWN_SEC:
            await self._say(msg.user_name, "Кубик можно бросать раз в 5 минут. Подожди немного!")
            return

        balance = await self.points.get_balance(uid)
        if balance < DICE_COST:
            await self._say(
                msg.user_name,
                f"У тебя недостаточно средств. Бросок стоит {DICE_COST} принцесс. Извини :(",
            )
            return

        await self.points.add(uid, -DICE_COST)
        await self.dice_cooldowns.set_last(uid, now)
        roll = random.randint(DICE_ROLL_MIN, DICE_ROLL_MAX)

        if roll == DICE_CRITICAL_FAIL:
            balance = await self.points.get_balance(uid)
            await self.points.set_balance(uid, max(0, balance - DICE_CRITICAL_FAIL_PENALTY))
            await self._say(
                msg.user_name,
                f"{DICE_CRITICAL_FAIL}. Критический провал! С твоего баланса списаны "
                f"{DICE_CRITICAL_FAIL_PENALTY} принцесс. "
                "Любое получение принцесс остановлено на 5 минут",
            )
        elif roll == DICE_CRITICAL_SUCCESS:
            await self.points.add(uid, DICE_CRITICAL_SUCCESS_REWARD)
            await self._say(
                msg.user_name,
                f"{DICE_CRITICAL_SUCCESS}. Критический успех! Поздравляю, "
                f"тебе начислены {DICE_CRITICAL_SUCCESS_REWARD} принцесс",
            )
        else:
            await self._say(msg.user_name, f"Ты бросил кубик, выпало {roll}")

    async def _cmd_steal(self, msg: ChatMessage) -> None:
        if not is_steal_allowed():
            await self._say(
                msg.user_name,
                "Красть можно только по средам и пятницам с 00:00 до 23:59",
            )
            return

        if len(self._viewers) < STEAL_MIN_VIEWERS:
            await self._say(
                msg.user_name,
                f"Вокруг слишком мало людей. Тебя могут заметить. Нужно минимум {STEAL_MIN_VIEWERS}",
            )
            return

        uid = msg.user_id
        async with self.steal.mutate_info(uid) as info:
            now = time.time()
            if now - info["last_time"] < STEAL_COOLDOWN_SEC:
                await self._say(msg.user_name, "Команду можно использовать раз в 10 минут.")
                return

            info["last_time"] = now
            info["attempts"] += 1
            update_chance(info)
            chance = info["chance"]

        roll = random.randint(1, STEAL_ROLL_MAX)
        if roll > chance:
            await self._say(msg.user_name, "Провал! Тебе не удалось ничего утащить.")
            return

        stolen = calculate_princess_amount(chance)
        candidates = [v for v in self._viewers if v != uid]
        if not candidates:
            await self._say(msg.user_name, "К сожалению, никто не в сети для кражи.")
            return

        victim_id = random.choice(candidates)
        victim_name = self._viewers[victim_id]["user_name"]
        victim_points = await self.points.get_balance(victim_id)

        if victim_points < VICTIM_MIN_BALANCE:
            msg_text = random.choice(POOR_VICTIM_MESSAGES).format(name=victim_name)
            await self._say(msg.user_name, msg_text)
        else:
            max_possible = max(0, victim_points - VICTIM_MIN_BALANCE)
            if max_possible == 0:
                await self._say(msg.user_name, "У жертвы почти ничего не осталось для кражи.")
                return

            stolen = random.randint(STEAL_AMOUNT_MIN, min(STEAL_AMOUNT_MAX, max_possible))
            await self.steal.execute_steal(uid, victim_id, stolen)

            await self._say(msg.user_name, f"Успех! Ты украл {stolen} принцесс у {victim_name}.")

        chance_to_prison = prison_chance_for_amount(stolen)
        if chance_to_prison and random.randint(1, STEAL_ROLL_MAX) <= chance_to_prison:
            await self.prison.imprison(uid)
            await self.steal.increment_jail_count(uid)
            prison_minutes = PRISON_DURATION_SEC // 60
            await self._say(msg.user_name, f"Ты попал(а) в тюрьму на {prison_minutes} минут!")

    async def _cmd_admin_points(self, msg: ChatMessage) -> None:
        if not self.admin_user_id or msg.user_id != self.admin_user_id:
            await self._say(msg.user_name, "Только администратор может списывать/начислять баллы")
            return

        parts = msg.text.split()
        if len(parts) != 3:
            await self._say(
                msg.user_name,
                "Используйте формат: !списать/начислить никнейм количество",
            )
            return

        command = parts[0].lower()
        target_nick = parts[1]
        try:
            amount = int(parts[2])
        except ValueError:
            await self._say(msg.user_name, "Количество должно быть числом")
            return

        target_uid: Optional[str] = None
        target_name: Optional[str] = None
        for vuid, data in self._viewers.items():
            if data["user_name"].lower() == target_nick.lower():
                target_uid = vuid
                target_name = data["user_name"]
                break

        if target_uid is None or target_name is None:
            await self._say(msg.user_name, f"Пользователь '{target_nick}' не найден в чате.")
            return

        balance = await self.points.get_balance(target_uid)
        if command == "!начислить":
            await self.points.set_balance(target_uid, balance + amount)
            await self._say(msg.user_name, f"{amount} принцесс были начислены {target_name}")
        elif command == "!списать":
            await self.points.set_balance(target_uid, max(0, balance - amount))
            await self._say(msg.user_name, f"{amount} принцесс были списаны со счета {target_name}")
        else:
            await self._say(msg.user_name, "Неверная команда.")

    # --- утилиты ---------------------------------------------------------
    async def _say(self, user_name: str, text: str) -> None:
        if self._reply is None:
            log.debug("Princess (no reply): %s, %s", user_name, text)
            return
        await self._reply(user_name, text)
