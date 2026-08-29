import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class N8nWebhookClient:
    """Deliver completed agent-run events without blocking chat responses."""

    def __init__(
        self,
        *,
        webhook_url: str,
        timeout_seconds: float,
        webhook_secret: str | None = None,
    ) -> None:
        self.webhook_url = webhook_url.strip()
        headers = {}
        if webhook_secret:
            headers["X-SupportFlow-Secret"] = webhook_secret

        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    async def dispatch(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        await self._send(payload)

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            response = await self._client.post(self.webhook_url, json=payload)
            response.raise_for_status()
            logger.info(
                "n8n webhook delivered for run %s with status %s",
                payload.get("run_id", "unknown"),
                response.status_code,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "n8n webhook delivery failed for run %s: %s",
                payload.get("run_id", "unknown"),
                exc,
            )

    async def aclose(self) -> None:
        await self._client.aclose()
