# Changelog

## 1.0.0 (Alpha) - 2026-03-12

- First open-source alpha release.
- Repository cleaned for third-party consumption:
  - removed internal planning/working docs
  - removed tracked bytecode artifacts
  - removed internal benchmark journals and snapshots
- Hardened service defaults:
  - optional token auth
  - localhost-focused CORS defaults
  - session TTL cleanup
- Improved runtime reliability and observability:
  - frame-aware extraction path
  - stable action/element ID behavior improvements
  - structured action/observe trace timing and warning events
  - trace export redaction of sensitive values
- Added release and community docs:
  - `docs/versioning.md`
  - `docs/publishing.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`

## 0.1.0 - 2026-03-10

- Initial end-to-end implementation:
  - Managed + attached runtime modes
  - Deterministic extraction engine
  - Action execution pipeline with validation
  - Stable ID matching and delta generation
  - Optional FastAPI local service
  - CLI for launch/attach/observe/act/inspect + portal interaction loop
  - Global runtime operations (`navigate`, `back`, `forward`, `reload`, `wait`)
  - Corpus harness baseline (`eval-corpus`) with YAML fixtures and scoring
  - Telemetry + debug trace export
  - Initial test coverage for core functionality
