# LumenForge Fast Export Baseline — Provenance and Static Comparison

**Status: BLOCKED before implementation. No migration branch created; no source or executable changed.**

## Protected artifacts
- Recovery ZIP SHA-256 reverified: 3e17193f2cc74077b411038b5b7e557bce1aa823ddb6a616334e02436c8629a4.
- Current recovered source archive SHA-256: aa25cd65b6fc6e6aac29a7c59f460f167807f700590724b3357c94a6953cd354.
- Current candidate modular executable: [local executable path omitted], 85,701,950 bytes, SHA-256 2d6030411631aa1e28e95fcd9f16f95445ed49a0d250c5c4899e139a50ec3336. Its preserved launch receipt says alive after 8s but no main-window handle/title; visual verification was not performed.
- Older release candidate executable: [local executable path omitted], 134,362,758 bytes, SHA-256 3ec942113e6270709e7c3100e15e361cadcfebbb43f3578f43fe07a43ce0c936. Release manifest says source_revision: UNVERIFIED.
- Neither candidate is proven to be the exact build currently tested by the user.

## Critical recovered-source hashes
| File | SHA-256 |
| lumenforge/engine.py | a3f4a6602e19c3f1ee9cd82527317f73a91f60924b4fa8aabb44a59db8c63891 |
| lumenforge/export.py | a2ab477757ac165eb1385bf512647bc2a2a86018ec84ac82abde54b93c5e1c96 |
| lumenforge/rendering.py | cfcf69052ea88fd0c07fc688ddec83e7269276b99564ac617d6835dd4dea5848 |
| lumenforge/app.py | e9145d73be5defb02cc058f5a4d20c5905fde7c2f53d6ec0ba2ae41acc7adbf0 |
| lumenforge/params.py | e953030298ef5e8dbbd09c7106a47b1f8bb3da800fcdb91077abd888d6a6a834 |
| lumenforge/project.py | 7d940e7f8a0a6dbd76c111c81674d14f12b164a6348fc1c8860544ff7d17389e |
| lumenforge/undo.py | 10951db9569c5018c59a3140f4a265d84b07eb7953ca57998c4be209571cc477 |
| lumenforge/config.py | c542455eb6e31328758a3a53fb204e7fe31bf39aad85933bed321e7e3d008480 |
| lumenforge/deps.py | 06725d3535acfa0e75ecb61b4ecd596eae91f4ce08d31edceb5e2dda69498ae8 |
| lumenforge/selftest.py | c5e4cfbd7a7b3113a2c47d780d02603b25dd3bab2bff7085587487b082a020b5 |
| pyproject.toml | 35d627c3470e4236a37cc48f47388f06c35dd1031b65d10b8b2cf0fc6d7e5a45 |
| run_lumenforge.py | ad8dfc2a952618961d2f4b10a8910ead866985077bd58b91523b082ed27a8457 |
| lumenforge.spec | 39e141afb9bb05deabe7d75545cb961c8875fcbc48c523fc97a5c1f9e3fc977f |
| tests/test_engine.py | 36bd73e146eb9e28936af8016c953bf4d65830a8cc07bc9f4a428c8e88389dda |
| tests/test_packaging_contract.py | 07586a9fb9dde0616c6523e3d4ec5a418c8e0c121e5cf42efaf02773d0dd65ee |

## Historical source found
- Archive: [local archive path omitted].
- Archive SHA-256: ce7b95e3eb8909fe1ca30fea6ab6044cecbf87616f6f7cb8a9af72bc2b6b261a.
- Extracted older monolithic source: comparison_old_release_source\source\lumenforge.py.
- Source SHA-256: 9dbaaa5fb1ff8bb5c403e5bbb5d0c1474f59195931daf8baedcbf7210a8457ab.
- This source is structurally different from the modular package and its release manifest does not pin a verified source revision. It is a comparison candidate, not a proven parent of the recovered source.

## Static call-graph observations
- Recovered export: ExportMixin._sx_ -> ExportMixin._ew -> ensure_rgb(self.src) -> staged(...) using row tiles only when staged_tile_safe(...) is true, otherwise full-frame staged(...) -> dithered(...) -> format-specific Pillow save.
- Recovered preview render: Eng.render caches camera/WB/tone/color layers. Its effects stage is explicitly uncached; grain remains stochastic.
- The export method calls staged(), not Eng.render(). Therefore the historical render effect-cache timing cannot be used to explain export speed.
- The older monolithic source contains Eng.render_bounded, bounded tile source/cache helpers, and explicit graph/tile contracts not present as the same entry points in the recovered modular engine. This is a real architectural difference, but no speed causality is inferred.
- Function-level source hashes and bounded unified-diff excerpts are in FAST_EXPORT_BASELINE_AND_SOURCE_COMPARISON.json.

## Historical performance evidence — not a valid before/after export pair
- The 2026-10-01 report records a representative 512×768 render at ~0.426 s before effect caching, ~0.0008 s for repeated unchanged renders after caching, ~0.009 s for exposure-only change after warm cache, and ~0.455 s for a spatial-effect change. These are render-stage timings, not a paired export benchmark.
- The 2026-10-03 export readback receipt records successful JPEG/PNG/TIFF artifacts at 6032×4028 but no elapsed export times.
- A repeatable three-run export benchmark has not been run because the exact user-tested executable, image fixture, settings, output format, and dimensions have not been identified as one matching set.

## Required before implementation
1. Preserve the exact executable/build that currently demonstrates fast export, plus its source archive/commit if available.
2. Preserve the exact test image (original bytes), settings/preset/project file, output format, dimensions, quality/compression options, and any RAW sidecar/XMP/LUT dependencies. Record SHA-256 hashes.
3. Identify which of the two executable candidates (if either) is the actual tested build, or provide the actual path/hash.
4. Once matched, run the same workload three times on each verified baseline/candidate, record cold/warm state, wall-clock timings, output dimensions/format, output hashes, and pixel/readback parity.
5. Only then document a defensible migration base and create the isolated migration branch.

## Safety state
- Recovery archive and recovered source unchanged.
- No migration branch created; no implementation started.
- No CUDA changes, merge, push, or release publication.
