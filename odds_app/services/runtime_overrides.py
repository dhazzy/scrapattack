from threading import Lock
from typing import Any

ALLOWED_OVERRIDE_KEYS: set[str] = {
    "scrape_recovery_retry_count",
    "scrape_recovery_backoff_sec",
    "scrape_min_quotes_success",
    "scrape_degraded_consecutive_failures",
    "scrape_degraded_cooldown_sec",
    "odds_drop_threshold_pct",
    "odds_drop_opening_threshold_pct",
    "odds_drop_confirmation_count",
    "odds_drop_confirmation_window_min",
    "odds_drop_renotify_improvement_pct",
}

_lock = Lock()
_overrides: dict[str, Any] = {}


def _normalize_value(key: str, value: Any) -> Any:
    if key in {
        "scrape_recovery_retry_count",
        "scrape_min_quotes_success",
        "scrape_degraded_consecutive_failures",
        "scrape_degraded_cooldown_sec",
        "odds_drop_confirmation_count",
        "odds_drop_confirmation_window_min",
    }:
        return int(value)
    if key in {
        "scrape_recovery_backoff_sec",
        "odds_drop_threshold_pct",
        "odds_drop_opening_threshold_pct",
        "odds_drop_renotify_improvement_pct",
    }:
        return float(value)
    return value


def get_runtime_overrides() -> dict[str, Any]:
    with _lock:
        return dict(_overrides)


def set_runtime_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(payload) - ALLOWED_OVERRIDE_KEYS)
    if unknown:
        raise ValueError(f"unknown override keys: {', '.join(unknown)}")
    normalized = {k: _normalize_value(k, v) for k, v in payload.items()}
    with _lock:
        _overrides.update(normalized)
        return dict(_overrides)


def clear_runtime_overrides() -> None:
    with _lock:
        _overrides.clear()

