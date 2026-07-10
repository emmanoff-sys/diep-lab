"""OA-091 — meter identity resolution.

Deterministic meter identity reconciliation mapping AMI-side meter IDs
to canonical (asset_id, asset_kind) pairs. Fail-fast construction
validates all mapping targets against the known canonical asset set per
OA-069 §8.
"""

from __future__ import annotations

from .framework import AMIConnectorError


class AMIMeterIdentityMap:
    """Maps AMI meter IDs to canonical (asset_id, asset_kind) pairs.

    Construction validates that every canonical ID referenced by the
    mapping exists in the supplied `known_asset_ids` frozenset, raising
    `AMIConnectorError` immediately if any target is unknown. This
    ensures misconfigured identity maps are detected at startup rather
    than at first event — fail-fast per OA-069 §8.

    `detect_ambiguities()` returns canonical asset IDs that appear more
    than once (multiple meters mapped to the same canonical ID is valid
    in AMI — multiple customers at one network node — but ambiguities
    are surfaced for operator awareness).
    `detect_missing()` returns meter IDs present in a batch but absent
    from the map.
    """

    def __init__(
        self,
        mapping: dict[str, tuple[str, str]],
        known_asset_ids: frozenset[str] | None = None,
    ) -> None:
        """mapping: {meter_id: (asset_id, asset_kind)}"""
        self._map = dict(mapping)
        if known_asset_ids is not None:
            unknown = {
                asset_id for asset_id, _ in self._map.values() if asset_id not in known_asset_ids
            }
            if unknown:
                raise AMIConnectorError(
                    "AMI meter identity map references unknown canonical IDs: "
                    + ", ".join(sorted(unknown))
                )

    def resolve(self, meter_id: str) -> tuple[str, str]:
        """Return (asset_id, asset_kind) or raise AMIConnectorError."""
        result = self._map.get(meter_id)
        if result is None:
            raise AMIConnectorError(f"meter ID not in identity map: {meter_id}")
        return result

    def detect_ambiguities(self) -> tuple[str, ...]:
        """Return canonical asset IDs that appear more than once in the map."""
        seen: dict[str, int] = {}
        for asset_id, _ in self._map.values():
            seen[asset_id] = seen.get(asset_id, 0) + 1
        return tuple(sorted(aid for aid, count in seen.items() if count > 1))

    def detect_missing(self, meter_ids: frozenset[str]) -> tuple[str, ...]:
        """Return meter IDs in the supplied set that are absent from the map."""
        return tuple(sorted(mid for mid in meter_ids if mid not in self._map))

    @property
    def mapped_meter_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._map))
