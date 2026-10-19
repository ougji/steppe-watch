# Contributions and experiment log

The initial v0.1 scaffold, synthetic example and tests were generated with assistance from ChatGPT/Codex on October 4, 2026.

Before presenting the project, run it, understand the core method and make concrete technical contributions. Track them here. Be ready to explain implementation choices, data provenance, results, failures and assistance used.

## Work to record

- Selecting the problem and pilot location.
- Collecting and preparing permitted imagery.
- Annotating reference masks and controlling data leakage.
- Designing and evaluating improvements.
- Interpreting false alerts and documenting limitations.
- Fixing issues found by users.

## Log

| Date | Question or task | Your change | Evidence or result | Next decision |
| --- | --- | --- | --- | --- |
| 2026-10-04 | Establish a runnable starter | AI-assisted scaffold; personal review pending | Synthetic demo and baseline tests | Run locally and choose real pilot data |
| 2026-10-14 | Upgrade the review and reproducibility workflow | Codex-assisted v0.2 implementation: shared pipeline, region inspection, reference evaluation, optional correction, portable exports, packaging and CI | Automated numerical, input, export/replay, CLI and app checks; synthetic data only | Personal review and documented real-data evaluation remain pending |
| 2026-10-19 | Preserve exact exported results | Codex-assisted threshold precision fix, per-pixel region-ID export and screenshot link repair | 47 tests pass, including execution of the exported command at a fractional score boundary; lint and formatting pass | Keep annotation coverage separate from detection exclusions |
| 2026-10-19 | Evaluate partial annotations without changing detection | Codex-assisted annotation coverage mask in Python, CLI, app and exports; evaluated coverage in schema 1.1 | 50 tests pass, including component filtering across unlabelled pixels, mask validation and replay; lint and formatting pass | Compare fixed settings across multiple independent pairs |
| 2026-10-19 | Compare fixed settings across a dataset | Codex-assisted v0.3 batch runner, strict manifests, pooled/macro metrics, per-case JSON/CSV and documented synthetic examples | 58 tests pass; CLI demo/ZIP and two-scenario benchmark succeed; includes undefined metrics and a correction failure on widespread change | Add independently annotated real image pairs; synthetic results establish no satellite accuracy |

Update this log with changes and outcomes as you complete them.
