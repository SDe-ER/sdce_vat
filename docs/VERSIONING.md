# Versioning, branches, upgrades and rollback

Status: policy for the `sdce_vat` app. No release exists yet.

## 1. Three independent versions
| Version | Where | Format | Changes when |
|---|---|---|---|
| App | git tag, `sdce_vat/__init__.py` `__version__` | `v16.MINOR.PATCH[-beta.N / -rc.N]` | every release |
| Calculation engine | `sdce_vat/engine/core.py` `ENGINE_VERSION` | `MAJOR.MINOR.PATCH` | a calculation result can change for the same inputs |
| Tax rule set | Saudi VAT Rule Set record | `<code>-<YYYY.N>`, e.g. `KSA-VAT-2026.1` | a legal or placement rule changes |

Every Saudi VAT Return stores the engine version and the rule sets (with content hash) used for its calculation.
A new app release never changes the result of an approved return.

## 2. App version series
The app follows the Frappe / ERPNext pattern: the major number is the supported framework major.
- `v16.x.y` = Frappe Framework 16 and ERPNext 16.
- Pre-releases: `v16.0.0-beta.N`, then `v16.0.0-rc.N`. The first planned pre-release is `v16.0.0-beta.1`.
- `v16.0.0` is the first stable release. It is tagged only when every item in
  [RELEASE_CRITERIA](RELEASE_CRITERIA.md) passes.
- After `v16.0.0`: MINOR (`v16.1.0`) adds features without breaking changes; PATCH (`v16.0.1`) fixes bugs only.
- Python `__version__` uses the PEP 440 form of the same version: `16.0.0b1`, `16.0.0rc1`, `16.0.0`.
- A future Frappe/ERPNext major starts a new series (`v17.0.0-beta.1`). Versions are never reused.

## 3. Branches
| Branch | Purpose |
|---|---|
| `main` | development for the current major (16) |
| `version-16` | created at the first release candidate; receives fixes for 16 releases |
| `feat/*`, `fix/*`, `docs/*` | work branches; merged into `main` by pull request only |
| `version-17` | created when work for Frappe/ERPNext 17 starts |

Rules:
- Every change reaches `main` or a `version-*` branch through a pull request.
- All required CI checks must pass. Merges are manual. No auto-merge.
- No force-push or deletion of protected branches. No history rewrite.
- Tags and GitHub releases are created only by a maintainer, after the release checklist passes.

## 4. Release checklist
1. CI green on the release commit (linters, Semgrep, secret scan, dependency audit, server tests).
2. Fresh install, upgrade from the previous tag and a second `bench migrate` pass on an isolated test site.
3. Uninstall and reinstall pass.
4. CHANGELOG entry: changes, impact, migrations, known limits, rollback.
5. Engine version bumped if results can change; listed in the CHANGELOG.
6. No claim of ZATCA certification or automatic filing.

## 5. Upgrades
- Read the CHANGELOG of every version between the installed and the target version.
- Take a verified site backup (database and files) before the upgrade.
- Upgrade on a staging copy first: `bench get-app` / `bench update` to the target tag, then
  `bench --site <site> migrate`, then run a second `migrate` (it must report no changes).
- Data patches are idempotent and covered by tests.
- Approved returns, snapshots and filings are never recalculated by an upgrade.

## 6. Rollback
- Code rollback (checking out the previous tag) does not undo data patches or new records.
- Full rollback = restore the pre-upgrade backup, then check out the previous tag and run `bench migrate`.
- If a release only changes code without patches, checking out the previous tag and restarting is enough; the
  release notes state which case applies.

## 7. Tax rule versions
- Published rule sets are never edited. A change is a new version.
- A corrective version may start on an earlier date only with a documented legal basis. It never changes an
  approved return: a review report shows its impact, and people decide on any amendment.
- The app ships baseline rules as Pending. Each organization verifies and publishes them (three different users:
  preparer, verifier, publisher).
