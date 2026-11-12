# Requirements Traceability Matrix

Produced by inspecting every controller, model and frontend component in the
submitted build **before** any changes were made, and comparing them against the
approved project proposal and the interim report.

Legend — **Status before this round of work:**
`DONE` implemented and correct · `PARTIAL` present but incomplete or wrong ·
`MISSING` not implemented · `BROKEN` present but defective/insecure

---

## Phase 1 — Critical bugs and security

| # | Requirement | Existing implementation | Missing or broken behaviour | Files involved | Priority |
|---|---|---|---|---|---|
| 1.1 | Only workers may apply for jobs | `ApplicationsController.Apply` guarded by `[Authorize]` only | **BROKEN** — any authenticated user (employer, organization, admin) can submit a worker application | `Controllers/ApplicationsController.cs` | Critical |
| 1.2 | Users must not apply to their own jobs | No check at all | **MISSING** — an employer could apply to their own posting | `Controllers/ApplicationsController.cs` | Critical |
| 1.3 | Reject applications to closed jobs | `job.Status != "open"` checked | `DONE` | `Controllers/ApplicationsController.cs` | — |
| 1.4 | Reject duplicate applications | Unique index + runtime check | `DONE` | `ApplicationsController.cs`, `AppDbContext.cs` | — |
| 1.5 | Valid status lifecycle pending→accepted→completed | `UpdateStatus` accepts any value from the allowed list | **BROKEN** — pending can jump straight to completed without hiring; completed can be reverted to pending/rejected | `Controllers/ApplicationsController.cs` | Critical |
| 1.6 | Atomic status + payment write | Two writes, single `SaveChanges`, no explicit transaction | **PARTIAL** — no transaction isolation around the payment creation | `Controllers/ApplicationsController.cs` | High |
| 1.7 | Reviews restricted to genuine counterparties | Author participation verified | **BROKEN** — `SubjectId` is never validated; a worker who completed job 5 can rate *any arbitrary user id*, including strangers | `Controllers/RatingsController.cs` | Critical |
| 1.8 | Review subject must exist | Not checked | **MISSING** | `Controllers/RatingsController.cs` | High |
| 1.9 | Star range 1–5 | Validated in controller and DTO | `DONE` | `RatingsController.cs`, `Dtos.cs` | — |
| 1.10 | Prevent double payment of the same record | `MarkPaid` sets status unconditionally | **BROKEN** — re-calling overwrites `PaidAt`, destroying the original timestamp | `Controllers/PaymentsController.cs` | Critical |
| 1.11 | Payment audit trail | None | **MISSING** | `Models/Payment.cs` | High |
| 1.12 | JWT secret kept out of the repository | Literal key committed in `appsettings.json` | **BROKEN** — production secret in source control | `appsettings.json`, `Program.cs` | Critical |
| 1.13 | Demo credentials not shown publicly | Admin email + password printed on the login page | **BROKEN** | `frontend-src/app.jsx` | Critical |
| 1.14 | Login rate limiting | None | **MISSING** — unlimited password guessing | `Program.cs`, `AuthController.cs` | High |
| 1.15 | Password strength rules | Minimum length 6 only | **PARTIAL** | `AuthController.cs`, `Dtos.cs` | Medium |
| 1.16 | Role change invalidates stale privileges | Old JWT keeps the previous role until expiry | **BROKEN** | `TokenService.cs`, `Program.cs` | High |
| 1.17 | Deleting a user preserves financial history | Hard delete removes jobs, applications, payments | **BROKEN** — destroys payment records and reviews | `Controllers/AdminController.cs` | Critical |

## Phase 2 — Missing proposal requirements

| # | Requirement | Existing implementation | Missing or broken behaviour | Files involved | Priority |
|---|---|---|---|---|---|
| 2.1 | Intelligent job recommendations | None | **MISSING** — a headline objective of the proposal | new `RecommendationService.cs`, `RecommendationsController.cs` | Critical |
| 2.2 | Advanced filtering (wage range, skills, availability, sorting) | Keyword, category and location only | **PARTIAL** | `Controllers/JobsController.cs` | High |
| 2.3 | Organization verification workflow | No verification concept exists | **MISSING** — "Verified Employer" badge shown to everyone unconditionally | `Models/User.cs`, new `OrganizationController.cs`, `AdminController.cs` | Critical |
| 2.4 | Organization-specific management | Organizations reuse employer screens | **PARTIAL** | `EmployerController.cs`, frontend | Medium |
| 2.5 | Worker profile: experience, certifications, district | Skills, location, bio only | **PARTIAL** | `Models/User.cs`, `ProfileController.cs` | High |
| 2.6 | Employer can edit a job after posting | Create and close only | **MISSING** | `Controllers/JobsController.cs` | High |
| 2.7 | Job dates, workers required, required skills | Not modelled | **MISSING** | `Models/Job.cs` | High |
| 2.8 | Daily wage / work tracking (days worked, outstanding balance) | Single flat `Pay` copied to the payment | **MISSING** — cannot record multiple days or part payment | new `WorkRecord.cs`, `Models/Payment.cs` | Critical |
| 2.9 | Decimal precision for money | `decimal` in C#, converted to `double` for SQLite | **BROKEN** — floating-point storage for monetary values | `Data/AppDbContext.cs` | High |
| 2.10 | Worker confirmation of payment | Employer marks paid; worker has no say | **MISSING** | `Models/Payment.cs`, `PaymentsController.cs` | High |
| 2.11 | Notifications for newly posted relevant jobs | Only application/hire/pay events | **PARTIAL** | `JobsController.cs`, `RecommendationService.cs` | High |
| 2.12 | Reports and analytics with export | Headline counters only | **MISSING** | new `ReportsController.cs` | High |
| 2.13 | Admin job-category management | Categories hardcoded in the frontend | **MISSING** | new `JobCategory.cs`, `CategoriesController.cs` | Medium |
| 2.14 | Dedicated job details page | Job cards only; `GET /api/jobs/{id}` unused by the UI | **MISSING** | `frontend-src/app.jsx` | Medium |
| 2.15 | Honest homepage statistics | `Math.Max(real, 10000)` etc. | **BROKEN** — fabricated adoption figures | `Controllers/StatsController.cs` | Critical |
| 2.16 | Working contact form | `setSent(true)` with no network call | **BROKEN** — false success message, nothing stored | `frontend-src/app.jsx`, new `ContactController.cs` | High |
| 2.17 | Testimonials labelled honestly | Three invented testimonials presented as real | **BROKEN** | `frontend-src/app.jsx` | High |
| 2.18 | Pricing page claims match reality | Advertises unimplemented features | **BROKEN** | `frontend-src/app.jsx` | Medium |

## Phase 3 — Database

| # | Requirement | Existing | Missing | Files | Priority |
|---|---|---|---|---|---|
| 3.1 | EF Core migrations | `EnsureCreated()` only | **MISSING** — schema cannot evolve without deleting the database | `Program.cs`, new `Migrations/` | Critical |
| 3.2 | Safe upgrade path for existing SQLite files | None | **MISSING** | `Program.cs` | Critical |
| 3.3 | Foreign-key integrity across new tables | Existing relationships sound | extend to new entities | `Data/AppDbContext.cs` | High |

---

## Summary of the pre-work state

- **17** critical or high-severity defects in authorization, workflow integrity and financial correctness.
- **4** headline proposal objectives entirely absent: job recommendations, organization verification, reporting, and daily-wage work tracking.
- **5** places where the interface claimed something the system did not do (verified badges, homepage adoption figures, testimonials, the contact form, pricing features).

Every row above is addressed in `CHANGELOG-AUDIT.md`, which records what was
changed and which rows remain open.
