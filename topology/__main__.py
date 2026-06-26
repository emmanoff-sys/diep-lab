"""CLI: python -m topology <file.geojson> --root <node_id> --label <label>

Imports a GeoJSON network export into grid_nodes/grid_edges, publishing a
new network_model_version. `--root` is the imported node that connects
upstream to the rest of the network (see geojson.orient_radial — there is
no reliable way to infer this from the file alone).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import geojson, loader


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m topology")
    p.add_argument("file", help="GeoJSON FeatureCollection to import")
    p.add_argument("--root", required=True, help="node_id of the upstream connection point")
    p.add_argument("--label", required=True, help="label for the published network_model_version")
    p.add_argument("--description", default=None)
    p.add_argument("--site", default=None, help="site_name to stamp on imported nodes")
    p.add_argument("--created-by", default="topology-importer")
    p.add_argument("--dry-run", action="store_true",
                    help="parse + orient only, print the summary, write nothing")
    args = p.parse_args(argv)

    with open(args.file) as fh:
        fc = json.load(fh)
    parsed = geojson.parse_feature_collection(fc)
    if parsed["unresolved"]:
        print(f"WARNING: {len(parsed['unresolved'])} unresolved feature(s):", file=sys.stderr)
        for u in parsed["unresolved"]:
            print(f"  - {u}", file=sys.stderr)

    oriented = geojson.orient_radial(parsed["nodes"], parsed["edges"], root_id=args.root)
    if oriented["unreached"]:
        print(f"WARNING: {len(oriented['unreached'])} node(s) not reachable from "
              f"--root {args.root}: {oriented['unreached']}", file=sys.stderr)

    print(f"parsed: {len(parsed['nodes'])} nodes, {len(oriented['edges'])} edges, "
          f"{len(parsed['unresolved'])} unresolved, {len(oriented['unreached'])} unreached")

    if args.dry_run:
        return 0

    result = loader.import_parsed(
        parsed["nodes"], oriented["edges"], label=args.label, description=args.description,
        site_name=args.site, created_by=args.created_by,
    )
    print(f"published version {result['version']['version']} ({args.label}): "
          f"{result['nodes_written']} nodes, {result['edges_written']} edges written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
