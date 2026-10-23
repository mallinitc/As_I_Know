from __future__ import annotations

import logging
import threading
from datetime import timedelta
from time import monotonic
from typing import Callable


logger = logging.getLogger("arca.api")

# Mint a replacement this long before the current key lapses so an in-flight
# request never carries a key that expires mid-call.
REFRESH_MARGIN_SECONDS = 300

TokenGenerator = Callable[[str, int], str]


def _default_generator(region: str, ttl_seconds: int) -> str:
    # Imported lazily so deployments that do not use Bedrock need no AWS packages.
    from aws_bedrock_token_generator import provide_token

    # Credentials come from the standard AWS chain (environment, profile, SSO,
    # or the EC2/ECS role). The key's real validity is the shorter of ttl_seconds
    # and the remaining lifetime of those credentials.
    return provide_token(region=region, expiry=timedelta(seconds=ttl_seconds))


class BedrockTokenError(RuntimeError):
    pass


class BedrockTokenProvider:
    """Caches one short-lived Bedrock API key and replaces it before it expires."""

    def __init__(
        self,
        region: str,
        ttl_seconds: int,
        generator: TokenGenerator | None = None,
        clock: Callable[[], float] = monotonic,
    ):
        self.region = region
        self.ttl_seconds = ttl_seconds
        self._generator = generator or _default_generator
        self._clock = clock
        self._lock = threading.Lock()
        self._token = ""
        self._refresh_at = 0.0

    def token(self) -> str:
        with self._lock:
            if not self._token or self._clock() >= self._refresh_at:
                self._mint()
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = ""
            self._refresh_at = 0.0

    def _mint(self) -> None:
        started = self._clock()
        try:
            token = self._generator(self.region, self.ttl_seconds)
        except Exception as exc:
            # The exception text can include credential or profile details; log the type only.
            logger.warning("Bedrock key generation failed region=%s error=%s", self.region, type(exc).__name__)
            raise BedrockTokenError("A short-lived Bedrock key could not be generated from the available AWS credentials.") from exc
        if not token:
            raise BedrockTokenError("A short-lived Bedrock key could not be generated from the available AWS credentials.")
        self._token = token
        self._refresh_at = started + max(self.ttl_seconds - REFRESH_MARGIN_SECONDS, self.ttl_seconds / 2)
        logger.info("Bedrock short-lived key generated region=%s ttl_seconds=%s", self.region, self.ttl_seconds)


_providers: dict[tuple[str, int], BedrockTokenProvider] = {}
_providers_lock = threading.Lock()


def bedrock_token_provider(region: str, ttl_seconds: int) -> BedrockTokenProvider:
    # Gateways are built per request, so the cached key lives at module level.
    key = (region, ttl_seconds)
    with _providers_lock:
        provider = _providers.get(key)
        if provider is None:
            provider = _providers[key] = BedrockTokenProvider(region, ttl_seconds)
        return provider
