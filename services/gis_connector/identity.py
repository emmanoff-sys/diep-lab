"""OA-084 — GIS asset identity resolution.

Deterministic mapping from GIS external feature IDs to canonical asset
IDs. Validated at construction time; raises on startup if any mapping
target is unknown (fail-fast, consistent with OA-069 §8).
"""

from __future__ import annotations

from services.scada_connector.framework import SCADAConnectorError


class GISAssetIdentityMap:
    """Maps GIS external feature IDs to canonical asset IDs.

    mapping format: {gis_id: (canonical_id, asset_kind)}
    where asset_kind is "node" or "edge".
    """

    def __init__(
        self,
        mapping: dict[str, tuple[str, str]],
        known_asset_ids: frozenset[str] | None = None,
    ) -> None:
        self._map = dict(mapping)
        if known_asset_ids is not None:
            unknown = {cid for cid, _ in self._map.values() if cid not in known_asset_ids}
            if unknown:
                raise SCADAConnectorError(
                    "GIS identity map references unknown canonical IDs: "
                    + ", ".join(sorted(unknown))
                )

    def resolve(self, gis_id: str) -> tuple[str, str]:
        """Return (canonical_id, asset_kind) or raise SCADAConnectorError."""
        result = self._map.get(gis_id)
        if result is None:
            raise SCADAConnectorError(f"GIS feature ID not in identity map: {gis_id}")
        return result

    def detect_ambiguities(self) -> tuple[str, ...]:
        """Return canonical IDs that appear more than once (mapping collision)."""
        seen: dict[str, int] = {}
        for cid, _ in self._map.values():
            seen[cid] = seen.get(cid, 0) + 1
        return tuple(sorted(cid for cid, count in seen.items() if count > 1))

    def detect_missing(self, gis_ids: frozenset[str]) -> tuple[str, ...]:
        """Return GIS IDs present in the given set but absent from this map."""
        return tuple(sorted(gid for gid in gis_ids if gid not in self._map))

    @property
    def mapped_gis_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._map))
