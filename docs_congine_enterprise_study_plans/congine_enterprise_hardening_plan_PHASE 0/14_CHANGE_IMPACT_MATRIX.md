# 14 — Change Impact Matrix

## Purpose

Map recommended decisions to likely existing code/document areas. Claude Code must re-locate symbols at current HEAD rather than trusting historical line numbers.

| Decision | Likely current area | Change type | Risk | Required verification |
|---|---|---|---|---|
| Runner health through port | `adapters/dependency_injection.py`, `ports/validation_runner.py` | Small behavior/interface cleanup | Low | Minimal Protocol implementation + health tests |
| `is_enforced()` / result semantics | `domain/models.py`, `usecases/validate_contract_usecase.py` | Public additive API | Medium | All failure/posture combinations |
| Load-shed reason | `infrastructure/bounded_executor.py`, validation use case, models | Exception/result semantics | Medium | Saturation benchmark + strict/degrade tests |
| Timeout single source | config/defaults/use-case constructor | Default behavior cleanup | Medium | Constructor/config parity test |
| Serialization fail-closed | validation use case size guards | Security behavior | High | Unserializable/oversize boundary tests |
| Unknown type rejection | `domain/validator.py`, schema vocabulary/admission path | Contract semantics | High/breaking for invalid contracts | Load/admission tests, migration note |
| Dotted key safety | validator + schema vocabulary/admission | Contract semantics | High | Known false-safety reproduction |
| Contract language version | contract metadata/loader/compiler | New compatibility layer | Medium | v1 fixtures, version rejection/migration tests |
| Regex semantic versioning | validator/compiler/docs | Future breaking language change | High | Preserve v1 golden corpus |
| `null_forbidden` lifecycle | validator/schema docs | Compatibility/deprecation | Medium | Existing contract fixtures |
| Public unenforced scanner | package `__init__`, domain exports | Public API additive | Low | import/API test |
| Contract compiler facade | new domain/use-case modules | New architecture seam | Medium | compile valid/invalid contract tests |
| Semantic budget separation | config + validation orchestration | Behavior/config | Medium/High | latency/degradation measurements |
| Composition transactional cleanup | `dependency_injection.py` + resource owners | Lifecycle | High | failure injection + thread/client inspection |
| `atexit.unregister` | cache/executor/bus/sync components | Lifecycle | Medium | repeated create/destroy test |
| Telemetry shutdown ordering | `queue_event_bus.py` | Concurrency | Medium | active-ship shutdown test |
| Strict bool parsing | `config.py` | Config semantics | Medium | malformed env table |
| `contract_source` enum | config/container wiring | Config/public type | Medium | every source mode + typo |
| Empty local path rejection | config/container wiring | Config semantics | Low | unset/empty/valid path tests |
| Regional endpoint safety | config | Security/deployment | High | no placeholder endpoint use |
| RE2 sanitizer | `pii_sanitize.py` | Security implementation | Low/Medium | compatibility + adversarial input tests |
| Windows dev-only | docs/CI/security tests | Support policy | Low code, high product clarity | support matrix |
| Blocking mypy | pyproject/CI | Engineering gate | Medium initial cleanup | clean mypy run |
| Branch coverage | pytest/coverage config/CI | Verification | Low | baseline report |
| pip-audit/SBOM | CI/release | Supply chain | Low | scan artifact/report |
| Example correction | `examples/LangChain/...` | Developer experience | Low | example execution |
| Durable event interface | ports/infrastructure | Future architecture | Medium | no L2/L3 judgment dependency |
| Event schema version | durable event model | Future compatibility | Medium | migration/replay test |
| Tamper-evident chain | event store | Security/evidence | Medium | chain verification/tamper test |
| Tenant-scoped queries | history/event store | Security | High | cross-tenant denial tests |
| MCP | L5 adapters/new transport | Future integration | Medium | same core verdict as SDK |
| CLI/CI | L5 adapters | Future integration | Medium | canonical result equivalence |
| Correction hints | `BreachDetail`, deterministic mapping | Additive domain feature | Low/Medium | golden hint tests |
| Agent adapters | new L1/L4 | Future integration/security | Medium | canonical normalization tests |
| Capability profiles | event queries/aggregates | Analytics | Medium | minimum sample/confidence tests |
| Architecture graph | new domain/use case | Future differentiation | High domain complexity | deterministic graph fixtures |
| Control Plane API | later NestJS/Postgres | Future service | High | repository-interface contract tests |
| ADR/doc reconciliation | architecture/docs/prompts | Documentation correctness | High for trust | source-commit verification |

---

## Change grouping rule

Do not combine rows merely because they touch the same file.

For example, `config.py` may be touched by boolean strictness, contract-source enum, timeout source, regional routing, and semantic budgets. These are different semantic decisions and should remain separable in review/commits where practical.
