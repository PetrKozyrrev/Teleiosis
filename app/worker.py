"""Воркер напоминаний. Запуск: python -m app.worker (во втором терминале).

Раз в минуту проверяет, кому пора отправить ежедневную подборку.
Рассчитан на один процесс: второй экземпляр не стартует (advisory-блокировка PostgreSQL).
После изменений кода его нужно перезапускать вручную."""

import logging
import signal
import threading
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import MIN_SECRET_KEY_LENGTH, settings
from app.db import SessionLocal, engine
from app.digest import process_due_users

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 60
LOCK_KEY = 7_000_001  # произвольное число: общий ключ блокировки воркера


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if len(settings.secret_key) < MIN_SECRET_KEY_LENGTH:
        raise SystemExit(
            f"SECRET_KEY не задан или короче {MIN_SECRET_KEY_LENGTH} символов в .env"
        )

    # Блокировка живёт, пока открыто это соединение (то есть пока жив процесс)
    lock_connection = engine.connect()
    acquired = lock_connection.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
    ).scalar()
    lock_connection.commit()  # блокировка сессионная, переживает commit
    if not acquired:
        lock_connection.close()
        raise SystemExit("Воркер уже запущен: другой процесс держит блокировку")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    logger.info("Воркер запущен, проверка раз в %s с", INTERVAL_SECONDS)

    while not stop.is_set():
        try:
            with SessionLocal() as db:
                report = process_due_users(db, datetime.now(timezone.utc))
            if report.sent or report.failed:
                logger.info("Подборки: отправлено %s, не отправлено %s", report.sent, report.failed)
        except Exception as exc:  # проход не должен убивать воркер
            logger.error("worker pass failed: %s", type(exc).__name__)
        stop.wait(INTERVAL_SECONDS)

    lock_connection.close()
    logger.info("Воркер остановлен")


if __name__ == "__main__":
    main()