# DailyWork Flask + MySQL + Bootstrap conversion (work in progress)

**Do not deploy this branch or merge into main.** The original ASP.NET Core and React application must remain online until all existing features and real-backend tests pass against Flask.

Target stack: Flask, SQLAlchemy, PyMySQL, MySQL 8, Jinja2 templates, Bootstrap 5, JavaScript, Alembic migrations, bcrypt-compatible hashes.

Migration has three safety gates:
1. Mirror all 12 Entity Framework tables exactly (preserve existing PascalCase column names, foreign keys, unique indexes, timestamps, CV BLOBs and BIGINT storage for money and work units scaled by 100).
2. Port all 16 existing controllers and React screens with matching API payloads, permissions and lifecycle rules.
3. Pass actual MySQL end-to-end tests, verify records against source backups and rehearse rollback.

**What exists so far:** A separate protected work branch, a schema conversion in progress and a local implementation package with initial Flask routes and Bootstrap pages. Full feature parity, MySQL integration, real backend tests, email/CV lifecycle and production deployment are **not yet complete**. No data, secrets or existing application files were modified.

Source of truth: `backend/DailyWork.Api/Data/AppDbContext.cs`, `backend/DailyWork.Api/Models`, all files under `backend/DailyWork.Api/Controllers`, `frontend-src/app.jsx` and `docs/test-evidence/test_real_backend.py`.

Do not point development Flask at the production SQLite/PostgreSQL database. Database migration must be read-only on the original and write only into a new, empty MySQL schema.

To complete: port remaining API modules (profile/CV, recommendations, notifications, categories, contact, employer, organization, projects, ratings, reports/CSV/email, statistics, administration); convert remaining frontend screens; add test parity and release documentation.
