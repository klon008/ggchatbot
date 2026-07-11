"""Настройки рулетки (шаблон).

Скопируйте в settings.py и меняйте под свой канал.
settings.py не попадает в git и сохраняется при update.cmd.
"""

MIN_BANK_TO_START = 5000
BANK_RESET_AMOUNT = 50000

ROULETTE_MIN_BET = 1
ROULETTE_MAX_BET = 10000
ROULETTE_MAX_NUMBERS = 18

ROULETTE_COLLECT_SEC = 60
ROULETTE_COLLECT_MANUAL_SEC = 300
ROULETTE_COOLDOWN_SEC = 180
ROULETTE_SPIN_DELAY_SEC = 10  # Пауза после закрытия ставок (заглушка под анимацию)
