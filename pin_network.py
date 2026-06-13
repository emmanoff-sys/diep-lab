#!/usr/bin/env python3
"""Pin every DIEP compose file to a shared external network 'diep-net'.

Previously all containers shared the auto-created 'diep-lab_default' network
only by coincidence (same derived project name). This makes the shared network
explicit and authoritative by overriding each project's default network to a
fixed external one. Idempotent: skips files already pinned.
"""
import glob
import os

BLOCK = """
networks:
  default:
    name: diep-net
    external: true
"""

ROOT = "/home/emmanuel/diep-lab"

changed, skipped = [], []
for path in sorted(glob.glob(os.path.join(ROOT, "docker-compose*.yml"))):
    with open(path) as f:
        content = f.read()
    if "name: diep-net" in content:
        skipped.append(os.path.basename(path))
        continue
    if not content.endswith("\n"):
        content += "\n"
    content += BLOCK
    with open(path, "w") as f:
        f.write(content)
    changed.append(os.path.basename(path))

print("pinned:", ", ".join(changed) or "(none)")
print("already pinned:", ", ".join(skipped) or "(none)")
