# DailyWork Flask + MySQL + Bootstrap migration (IN PROGRESS)

Source baseline: [Samiru44/dailywork-full-system](https://github.com/Samiru44/dailywork-full-system) `main`, inspected 2026-11-20. Original ASP.NET Core/React system stays untouched.

**NOT READY FOR PRODUCTION OR FOR REPLACEMENT OF THE ORIGINAL SYSTEM.** This is a real initial conversion, not a complete feature-parity port. Do not point it at a live database or switch DNS yet.

## Implemented here

- MySQL-compatible SQLAlchemy 2 mapping for all **12** persistent EF Core DbSets, 153 columns, indexes and key foreign keys.
- Equivalent integer-cents and hundredths-of-a-work-unit storage via `Scaled100` (round-half-away-from-zero). MySQL tables and columns retain EF Core naming conventions (`Users`, `PasswordHash`, etc.).
- Configurable Flask app, bcrypt-compatible passwords, JWT authentication, role checking, security stamps, basic login throttling, basic cookie session with CSRF validation.
- API: `auth` (register/login); `jobs` (search/detail/create/update/close); `applications` (apply/mine/job/status/add work/decide work/view work); `payments` (mine/audit/pay/confirm/dispute).
- First Bootstrap/Jinja2 screens: public homepage, job browsing, job detail, register, login, role-aware summary dashboard.
- Fail-safe, read-only SQLite-to-empty-MySQL transfer utility. Verifies source/destination tables, columns, row counts, aggregate scaled amount totals and CV bytes digest.
- Seven **local** schema/migration tests (SQLite fixtures, not Flask HTTP or MySQL integration tests).

## NOT yet migrated (blocking launch)

- Profile and CV HTTP endpoints, recommendation scoring and notifications UI, employer/organization/project pages and API, categories, contact messages, ratings, reports/CSV/email, administrative pages, system and email notifications, scheduled/background email, full Bootstrap interactivity and all current React views.
- Existing API response parity is not yet tested against the live ASP.NET backend. Some implemented routes are preliminary and require edge-case verification (especially payment and employment lifecycles).
- MySQL integration tests, browser tests, concurrent payment tests, accessibility/visual comparison, production deployment and email integration.
- Direct PostgreSQL-to-MySQL transfer (the current data-transfer utility supports only SQLite files).
- The default Bootstrap stylesheet is loaded through a CDN; bundle a fixed, reviewed version for production.

## Safe local setup

Use Python 3.11+ and **a new empty MySQL 8 database** (never the original). From this folder:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Configure DATABASE_URL, DAILYWORK_JWT_KEY and FLASK_SECRET_KEY in the environment.
# Example: mysql+pymysql://dailywork_user:YOUR_PASSWORD@localhost:3306/dailywork_flask?charset=utf8mb4
python -m scripts.create_schema                   # inspect DDL: NO CHANGES
python -m scripts.create_schema --apply           # ONLY with a fresh, empty MySQL schema
python run.py
```

For schema/migration unit tests:

```bash
python -m pytest -q tests/test_models.py tests/test_migration.py
```

## Optional copy of *real* legacy SQLite data

1. Stop writes on the original system, take a consistent **offline backup** of `dailywork.db` (including WAL, if applicable) and retain the original backup elsewhere.
2. Prepare a new empty MySQL database and carefully review `scripts.create_schema --apply` before running it.
3. `python -m scripts.migrate_data --sqlite /path/to/SNAPSHOT.db` (checks only, **no writes**).
4. When checks pass and cutover is properly scheduled: `python -m scripts.migrate_data --sqlite /path/to/SNAPSHOT.db --apply`.
5. Compare per-table record counts, amounts and CV digests. Test existing password verification, end-to-end work/payment workflows and rollback before launch.

This tool fails closed when destination tables contain rows, expected columns are missing, or money is not in integer cents. The source is always read-only. It does not make a PostgreSQL export automatically. Migration must use the actual app database, not Visual Studio's `.vs` workspace SQLite database.

## Testing and release gate

**Do not replace `main` or the deployed .NET system until all 16 original controllers and the complete React interface have been ported and verified.** Run original ASP.NET test suite on real backend first. Adapt `docs/test-evidence/test_real_backend.py` to test both original and new backends. Check money (cents), auth/role changes, CV bytes, payment audit, partial payments and worker acknowledgements, emails and recommendations; then perform a rollback rehearsal with a consistent database snapshot.

No database contents, customer data or secrets have been committed here. This starter can be used as a migration branch; it is not a finished production conversion.
