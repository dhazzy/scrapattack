import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.models import Alert

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self) -> None:
        settings = get_settings()
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    async def send(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.info("Telegram credentials not configured. Skipping send: %s", message)
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.error("Telegram send failed: %s", resp.text)
                return False
        return True


def list_unsent_alerts(db: Session, limit: int = 50) -> list[Alert]:
    stmt = select(Alert).where(Alert.is_sent.is_(False)).order_by(Alert.created_at.asc()).limit(limit)
    return list(db.scalars(stmt))


def mark_alert_sent(db: Session, alert: Alert) -> None:
    alert.is_sent = True
    alert.sent_at = datetime.now(timezone.utc)
    db.add(alert)
