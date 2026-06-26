"""MDM Duplicate Detection.

Detects three distinct duplicate signatures (spec requirement): duplicate
(tenant_id, device_id, timestamp_utc, sequence_number) — the contract's own
TelemetryEnvelope.dedup_key() — and duplicate correlation_id independently,
since a transport-level retry can resend the same correlation_id with a
*different* timestamp/sequence if a producer bug double-stamps a retry, and
conversely a sequence_number could theoretically repeat across a producer
restart with a fresh correlation_id. Checking both catches either failure
mode; "duplicate timestamps" alone (without sequence_number) is intentionally
NOT used as a key on its own — see contract doc §5: two measurements can
legitimately share a timestamp if they differ in sequence_number (a real
redelivery) is the only same-timestamp case that's actually a duplicate,
which the key already covers.

Bounded, in-process caches — see config.py:DEDUP_CACHE_SIZE. Not a substitute
for a shared store if MDM is ever scaled to multiple replicas (documented
gap, matches the same caveat already on ingestor's dedup cache).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from contracts import TelemetryEnvelope

from .config import Settings

POLICY_ANY = "any"                          # default: either signature alone is a duplicate
POLICY_KEY_ONLY = "key_only"                 # only (tenant,device,timestamp,sequence)
POLICY_CORRELATION_ONLY = "correlation_only"  # only correlation_id


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    matched_on: list[str] = field(default_factory=list)


class _BoundedSet:
    def __init__(self, max_size: int):
        self._store: "OrderedDict[object, None]" = OrderedDict()
        self.max_size = max_size

    def seen(self, key) -> bool:
        return key in self._store

    def add(self, key) -> None:
        self._store[key] = None
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)


class DuplicateDetector:
    def __init__(self, policy: str | None = None, cache_size: int | None = None):
        self.policy = policy or Settings.DEDUP_POLICY
        size = cache_size if cache_size is not None else Settings.DEDUP_CACHE_SIZE
        self._keys = _BoundedSet(size)
        self._correlation_ids = _BoundedSet(size)

    def check_and_record(self, envelope: TelemetryEnvelope) -> DuplicateCheckResult:
        """Checks for a duplicate AND records the envelope as seen (so a
        second identical call always reports a duplicate) — call exactly
        once per received envelope, not speculatively."""
        key = envelope.dedup_key()
        key_dup = self._keys.seen(key)
        corr_dup = self._correlation_ids.seen(envelope.correlation_id)

        matched: list[str] = []
        if key_dup:
            matched.append("timestamp_sequence")
        if corr_dup:
            matched.append("correlation_id")

        if self.policy == POLICY_KEY_ONLY:
            is_dup = key_dup
        elif self.policy == POLICY_CORRELATION_ONLY:
            is_dup = corr_dup
        else:  # POLICY_ANY
            is_dup = key_dup or corr_dup

        self._keys.add(key)
        self._correlation_ids.add(envelope.correlation_id)
        return DuplicateCheckResult(is_duplicate=is_dup, matched_on=matched)
