# `smartds_gso_rural_rdt2999.geojson` — provenance

**Source:** NREL/DOE SMART-DS (Synthetic Models for Advanced, Realistic
Testing: Distribution Systems and Scenarios) v1.0, Greensboro NC ("GSO")
region, "rural" area, `base_timeseries` scenario.

**Downloaded from:**
`https://oedi-data-lake.s3.amazonaws.com/SMART-DS/v1.0/2018/GSO/rural/scenarios/base_timeseries/geojson/rhs3_1247--rdt2999.json`
(Open Energy Data Initiative data lake), 2026-06-25.

**License:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/),
per the dataset's `data.gov` catalog entry. Attribution: National
Renewable Energy Laboratory (NREL).

**What it is:** one transformer-area extract of feeder `rhs3_1247` —
10 "Node" points, 2 "Transformer" points, 3 "Load" points, 7 "Line"
LineStrings (one of which is a normally-closed disconnect switch). It is
a genuine fragment of a larger synthetic feeder, not a complete
substation-to-customer tree — it has no substation of its own; node
`rdt2999-rhs3_1247x` is this fragment's upstream connection point toward
the rest of feeder `rhs3_1247` (used as `--root` when importing). This
file was chosen (over the other files in the same directory, which run
1.7–6.3 MB) specifically for its small size (~33 KB, 22 features), so it's
usable as a fast integration-test fixture rather than a full-scale import.

SMART-DS is itself a synthetic dataset (NREL's own framing: "realistic but
not real") — distribution lines connected to real building footprints, not
an as-built utility GIS extract. Used here as a stand-in public sample with
genuine GIS structure (geometry, electrical properties, switch state),
per the project ban on fabricating topology data that only *looks*
realistic.
