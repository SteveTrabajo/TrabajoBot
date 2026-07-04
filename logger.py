import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

Path("logs").mkdir(exist_ok=True)

# Rotates at UTC midnight to logs/bot.log.YYYY-MM-DD, keeps 7 days.
handler = TimedRotatingFileHandler(
    "logs/bot.log", when="midnight", backupCount=7, encoding="utf-8", utc=True
)
handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname)s] [%(name)s] %(message)s"))

logger = logging.getLogger("TrabajoBot")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
logger.addHandler(console_handler)
logger.propagate = False  # Prevent double logging
