# Changed Files and Bugs Fixed

## Round 3 — CV upload, Plans menu by role, email (12 November 2026)

Requested: a CV upload in the job seeker's profile, the payment plan menu shown
only to the right roles, and emails when jobs are applied for, accepted and
posted, and for reports. All done, and all covered by executed tests: see
`docs/TEST-RESULTS.md` and, for how each feature works and how to switch on
real email, `docs/CV-EMAIL-PLANS.md`.

### Added files

| File | Purpose |
|---|---|
| `Models/CvDocument.cs` | A worker's CV, in its own table so the file is only loaded when needed |
| `Services/CvRules.cs` | File type, size and signature checks; safe file names |
| `Services/EmailQueue.cs` | SMTP settings, delivery mode (outbox / SMTP / off), the queue controllers hand emails to |
| `Services/EmailDispatcher.cs` | Background service that sends or saves each email, so a mail failure never affects a request |
| `Services/EmailTemplates.cs` | One template per event; user-typed text is escaped in one place |
| `docs/CV-EMAIL-PLANS.md` | Feature guide and email setup |
| `docs/test-evidence/test_ui_cv_email.py` | 60 browser checks for the three features |
| `docs/test-evidence/test_phone_layout.py` | Phone layout sweep |

### Changed files

| File | Change |
|---|---|
| `Controllers/ProfileController.cs` | CV upload, download, remove, and download-by-id with access rules |
| `Controllers/ApplicationsController.cs` | Emails on apply (CV attached for the employer) and on every status change |
| `Controllers/JobsController.cs` | Emails the employer and matching workers when a job is posted |
| `Controllers/EmployerController.cs` | Applicants list says which applicants have a CV |
| `Controllers/ReportsController.cs` | `POST /api/reports/email`: a user's own report, to their own address, once a minute |
| `Dtos/Dtos.cs` | CV fields on the profile and applicant DTOs |
| `Data/AppDbContext.cs` | `CvDocuments` set, cascade delete, unique index on `UserId` |
| `Data/DatabaseBootstrapper.cs` | Creates `CvDocuments` on existing databases; nothing else touched |
| `Program.cs` | Registers the email settings, queue and background dispatcher |
| `appsettings.json` | `Smtp` section, empty by default; outbox folder `email-outbox` |
| `.gitignore` | Excludes `email-outbox/` |
| `frontend-src/app.jsx` | My CV panel; CV button for employers; `canSeePlans()` controls the Pricing and Plans links; **Email me this report** buttons |
| `frontend-src/style.css` | Phone-only layout fixes (see below) |
| `wwwroot/assets/app.js`, `style.css` | Rebuilt from the two files above |
| `docs/test-evidence/test_upgrade.py`, `test_ui.py` | Used hard-coded folders from this machine; now use the system temp folder, so they run on Windows |

Nothing was deleted, and no existing database column was changed.

### Bug fixed: phone layout

On phones, the signed-in header was wider than the screen and pushed the ☰
menu button off it. At 360 px a worker had 53 px of sideways scrolling and an
administrator 170 px. This was already present in the version received. The
fix is CSS only and applies only below 860 px wide, so the desktop layout is
unchanged. Details are in `docs/TEST-RESULTS.md`.

---

## Round 2 — supervisor feedback of 10 November 2026

Four issues were raised, plus one optional improvement. All five are done, and
each is covered by executed tests.

### 1. Work records could be added after completion, leaving the payment wrong

**The defect.** `POST /api/applications/{id}/work` accepted `accepted` *or*
`completed` as a valid state, but the payment had already been calculated at the
moment of completion and was never revisited. So an employer could log two more
days onto a finished job and the worker would still be owed the old amount, with
nothing in the system showing the discrepancy.

**The fix** — `ApplicationsController.cs`. Adding work after completion now does
one of two things, never nothing:

- **If no money has been paid yet**, the payment is *recalculated* from the work
  records (`AgreedRate × approved units`), the new amount is written to the audit
  trail as a `recalculated` entry, and the worker is notified that the amount
  changed and why.
- **Once any money has been paid**, the record is frozen and the request is
  refused with an explanation: record a separate payment for the extra work, or
  raise a dispute. Rewriting the amount under a part-paid record would corrupt a
  payment both sides had already acted on.

Covered by API area 23 (7 checks), including that the amount does *not* change
after a refusal.

### 2. Payment confirmation did not survive a later payment

**The defect.** `WorkerConfirmed` was a one-way boolean. A worker could confirm
after a part payment; the employer then paid the balance and the record still
read "confirmed by worker" — when the worker had never acknowledged the second
instalment. There was also no record of *how much* had been confirmed.

**The fix** — `Payment.cs`, `PaymentsController.cs`. Confirmation now covers an
amount, not the record as a whole:

- `ConfirmedAmount` records how much the worker has actually confirmed.
- Recording further payment sets `WorkerConfirmed` back to false whenever
  `AmountPaid > ConfirmedAmount`, and the audit entry says so.
- Confirming when nothing new has arrived is refused, with the outstanding
  balance stated.
- Both dashboards show the real position: *"You confirmed Rs. 2,000. A further
  Rs. 2,200 has since been recorded — please confirm it."* and, for the employer,
  *"Rs. 6,000 awaiting the worker's confirmation."* The button names the amount:
  **Confirm Rs. 2,200 More**.

Existing databases are back-filled: a payment already marked confirmed is treated
as having confirmed what was paid at that point, so nobody is asked twice.

Covered by API area 25 (11 checks) and browser section K (7 checks).

### 3. No Edit Job form in the employer dashboard

**The fix** — `app.jsx`. `PostJobForm` now takes an optional `job` prop and
becomes an edit form: fields are filled from the posting, the heading reads
*Edit Job — <title>*, and saving calls `PUT /api/jobs/{id}`. **My Jobs** has an
Edit button on every open posting. One component serves both cases, so the create
and edit forms cannot drift apart.

The server rules it already enforced are now surfaced: when workers have been
hired the form explains that the wage is fixed and that positions cannot drop
below the number hired. Cancelling discards the change.

Covered by API area 26 (5 checks) and browser section I (7 checks), including
that cancelling saves nothing.

### 4. Organizations had no functionality of their own

**The fix** — new `Project` model, `ProjectsController.cs`, and a **Projects**
tab shown only to organizations.

An individual employer posts a job at a time. An organization runs projects — a
site, a contract, a season — that need a number of people across several
postings. A project records what it needs (workers, budget, dates) and then
reports its real position:

- **Recruitment tracking**: positions advertised, applicants, shortlisted, hired,
  still needed, and a fill rate — all counted from the actual applications, with
  a progress bar per project.
- **Cost tracking**: committed, paid and outstanding, from the actual payments,
  against the budget, with an over-budget flag.
- Postings can be expanded to show each job's own hiring position.

Jobs carry an optional `ProjectId`, so ordinary employers and one-off
organization postings are unaffected. A posting can only be filed under a project
the caller owns. Deleting a project keeps every job, application, payment and
rating — the jobs simply stop belonging to a project.

Covered by API area 27 (17 checks) and browser section L (12 checks), including
that one organization cannot see or edit another's projects.

### Optional improvement: workers can submit their own working days

`WorkRecord` gained a `Status` of `approved` / `pending` / `rejected`. A day the
employer enters is approved immediately; a day the **worker** submits is pending
until the employer approves it, and a new **Work Approvals** tab lists what is
waiting. Only approved days count towards the amount owed, so a worker cannot
increase their own payment, and a rejected day never reaches it. Rejection takes
a reason, which the worker sees.

Covered by API area 24 (9 checks) and browser section J (3 checks).

### Also fixed in this round

- **`GET /api/recommendations` was open to any signed-in user.** An employer or
  administrator could request worker recommendations. Now `[Authorize(Roles =
  "worker")]`. Found by the new end-to-end script.
- **The database upgrader created tables *after* adding columns**, so a table
  created by a given run was missing any column added in the same release until
  the application was restarted — and would be queried in between with those
  columns absent. Tables are now created first. Found by the idempotency test.

---

## Round 1 — the original audit


Compared file-by-file against the project ZIP you supplied
(`DailyWork-FullSystem_1.zip`), by content hash.

**26 files added · 29 files modified · 0 files deleted · 32 files untouched**
(plus 26 screenshots under `docs/test-evidence/screens/`)

Nothing was removed, and the technology stack is unchanged: ASP.NET Core 8 Web
API in C#, Entity Framework Core 8, SQLite, React 18 served from `wwwroot`.

---

## Files added (14)

| File | Why |
|---|---|
| `backend/.../Controllers/RecommendationsController.cs` | Job recommendations for a worker, and suitable workers for a job |
| `backend/.../Controllers/OrganizationController.cs` | Organizations submit verification requests and read their status |
| `backend/.../Controllers/ReportsController.cs` | Worker, employer and admin reports, plus four CSV exports |
| `backend/.../Controllers/CategoriesController.cs` | Job categories as data instead of a hardcoded list |
| `backend/.../Controllers/ContactController.cs` | Stores contact messages; honeypot and rate limiting |
| `backend/.../Services/RecommendationService.cs` | The matching rules and their explanations |
| `backend/.../Services/PasswordPolicy.cs` | Password strength rules |
| `backend/.../Services/LoginThrottle.cs` | Failed-login lockout |
| `backend/.../Data/DatabaseBootstrapper.cs` | Upgrades an existing database in place without losing data |
| `backend/.../Models/WorkRecord.cs` | Days or shifts actually worked |
| `backend/.../Models/PaymentAudit.cs` | Append-only history of every payment change |
| `backend/.../Models/JobCategory.cs` | Category table |
| `backend/.../Models/ContactMessage.cs` | Contact form submissions |
| `docs/TRACEABILITY-MATRIX.md` | Every requirement mapped to its implementation |
| `backend/.../Controllers/ProjectsController.cs` | Organization projects and recruitment tracking |
| `backend/.../Models/Project.cs` | A project an organization recruits for |
| `build-frontend.js` | Compiles `app.jsx` when you change the website |

Also added for this submission: `docs/TEST-RESULTS.md`,
`docs/FEATURE-CHECKLIST.md`, `docs/DATABASE.md`, and `docs/test-evidence/`
(raw test output, the four test scripts and 22 screenshots).

## Files modified (24)

**Models** — `User.cs`, `Job.cs`, `JobApplication.cs`, `Payment.cs`
**Data** — `AppDbContext.cs`, `DbSeeder.cs`
**Controllers** — `AuthController.cs`, `JobsController.cs`,
`ApplicationsController.cs`, `PaymentsController.cs`, `RatingsController.cs`,
`ProfileController.cs`, `EmployerController.cs`, `AdminController.cs`,
`StatsController.cs`
**Services / startup** — `TokenService.cs`, `Program.cs`, `appsettings.json`,
`DailyWork.Api.csproj` (`<UseAppHost>false</UseAppHost>`, so Windows Application
Control has no unsigned `.exe` to block)
**DTOs** — `Dtos.cs`
**Frontend** — `frontend-src/app.jsx`, `frontend-src/style.css`, and the
compiled copies `wwwroot/assets/app.js`, `wwwroot/assets/style.css`
**Other** — `.gitignore`

---

# Bugs fixed

## Critical — security

### 1. Anyone could apply for a job, as any role

`POST /api/applications` carried a bare `[Authorize]`, so an **employer or even
an administrator could apply for jobs**, and an employer could apply to their own
posting. Nothing checked how many workers a job still needed, so a job for one
person could accept unlimited hires.

`ApplicationsController.cs` — now `[Authorize(Roles = "worker")]`, with an
explicit refusal for applying to your own posting and a check against
`WorkersNeeded` before an application is accepted.

### 2. Anyone could rate anyone, for any job

This was the most serious defect. `POST /api/ratings` accepted any `jobId` and
any `subjectId` from the request body and saved the rating. In practice:

- an employer could give a one-star review to a worker who had **never worked for
  them**, on a job that worker had never applied to;
- a worker could review an employer who had never hired them;
- either side could review the **same person repeatedly** and move their average
  rating to anything they liked;
- a rating could be left on a job that was never completed.

Because a worker's rating is the main thing an employer judges them by, this let
one account destroy another's standing on the platform.

`RatingsController.cs` — the author must be a genuine party to that specific job:
an employer may only review a worker whose application on **that job** reached
`completed`, and a worker may only review **the employer of that job**, and only
if their own application reached `completed`. A unique index on
`(JobId, AuthorId)` makes a second review of the same job impossible at the
database level.

### 3. Deactivating or demoting an account did nothing

Already-issued JWTs stayed valid until expiry, so a user who had been blocked, or
whose role had been changed, kept their old access.

`User.cs` gained a `SecurityStamp`; `TokenService.cs` writes it into the token;
`Program.cs` re-reads the user on every request through `OnTokenValidated` and
refuses the token if the account is inactive or the stamp has moved.

### 4. JWT signing key committed to the repository

`appsettings.json` contained the signing key in plain text. Anyone with the
source could mint a valid administrator token.

The key is gone from the file. `TokenService.JwtKey()` reads
`DAILYWORK_JWT_KEY` from the environment; failing that it generates a random key
once and writes it to `jwt-key.local.txt`, which `.gitignore` excludes. The old
committed key is therefore no longer in use.

### 5. Admin credentials printed on the login page

The login page displayed the administrator's email and password to every visitor.
Removed, and replaced with a link to the register page. The seeded administrator
password is now `Admin@12345` and is documented in the setup instructions only —
change it after first sign-in.

### 6. No password rules and no lockout

Any password was accepted, including `1`, and an attacker could try as many as
they wanted.

`PasswordPolicy.cs` requires at least 8 characters with a letter and a digit, and
rejects common passwords and passwords containing the user's own name or email.
`LoginThrottle.cs` locks an email/IP pair for 15 minutes after 5 failed attempts.

### 7. Internal errors returned to the browser

Unhandled exceptions returned full stack traces, exposing file paths and query
structure. `Program.cs` now logs the detail server-side and returns only
`{"message":"Something went wrong. Please try again."}`.

### 8. Deleting a user destroyed financial history

Administrative delete removed the row outright, taking the payment records of
work that really happened with it.

`AdminController.cs` now deactivates instead: `IsActive = false` with a reason
and a timestamp. The account can no longer sign in, their jobs close, but every
payment and rating survives. An administrator cannot deactivate their own
account.

## Critical — correctness

### 9. Application status could jump anywhere

`PUT /api/applications/{id}/status` wrote whatever string it was given. A
rejected application could be moved to `completed`; a `completed` one could go
back to `pending`, raising a second payment for the same work.

`JobApplication.cs` now holds the permitted transitions, and
`ApplicationsController.cs` refuses anything else:

```
pending     -> shortlisted, accepted, rejected
shortlisted -> accepted, rejected
accepted    -> completed, rejected
completed   -> (terminal)
rejected    -> (terminal)
```

### 10. A settled payment could be re-settled

`PUT /api/payments/{id}/release` could be called repeatedly on the same payment,
each call overwriting `PaidAt` and losing the real settlement date.

`PaymentsController.cs` refuses to touch a payment whose status is already
`paid`, and every change appends a row to `PaymentAudit` so the history cannot be
rewritten.

### 11. Payment amounts were typed in, not calculated

The amount owed was whatever the employer entered, with no link to the work done.
A three-day job could be recorded as a one-day payment with nothing to contradict
it.

`WorkRecord.cs` records each day or shift worked. When the employer verifies the
work, the payment is computed as `AgreedRate × sum(UnitsWorked)` from those
records, and the breakdown is shown to both sides (`3 day(s) at Rs. 2,400`).

### 12. Money stored as floating point

`Pay`, `Amount` and related columns were `REAL`. Sums drifted by fractions of a
cent, so a worker's reported earnings would not exactly equal what was recorded.

`AppDbContext.cs` converts every money value to a whole number of **cents** on
the way into the database and back on the way out. Totals are now exact.

### 13. Status and payment were written separately

The status update and the payment row were two independent saves. If the second
failed, a job was `completed` with no payment owed.

Both writes now happen inside one `BeginTransactionAsync` — either both land or
neither does.

### 14. The worker had no say in whether they were paid

The employer marked a payment paid and that was the end of it.

`PUT /api/payments/{id}/confirm` lets the worker confirm the money arrived, and
`PUT /api/payments/{id}/dispute` lets them record that it did not, with a note.
Until confirmed, the employer's view reads `awaiting worker confirmation`.
Part payments are supported, with the outstanding balance shown on both sides.

## Honesty defects your supervisor identified

### 15. "Verified Employer" badge shown without any verification

The badge was rendered for every employer. There was no verification process at
all.

There is one now: an organization submits its registration number and address
(`OrganizationController.cs`), an administrator reviews the queue and approves or
rejects with a note (`AdminController.cs`), and the badge renders only when
`VerificationStatus == "verified"`. The job details page states plainly when an
employer is **not** verified, and job search has a "verified employers only"
filter.

### 16. Homepage statistics used minimum display values

`StatsController` applied `Math.Max` floors, so an empty database still advertised
thousands of workers.

The floors are gone; the counts are read from the database. Because a fresh
install ships with demonstration accounts, the response also reports
`isDemoData` and `demoUserCount`, and the homepage prints a note saying how many
of the counted accounts are samples. *(The flag's first version flipped to false
after a single real registration while the counters still included 17 seeded
accounts; the browser test caught that and it was corrected.)*

### 17. The contact form lied

It called `setSent(true)` and showed "Message sent successfully" without making
any network request. Nothing was stored and nobody received anything.

`ContactController.cs` stores the message; the form shows success only after the
server accepts it; messages appear in the admin panel's inbox. A hidden honeypot
field and a per-IP rate limit handle spam.

### 18. The pricing page advertised features that do not exist

It presented subscription tiers as though billing worked. The page is now headed
**"Pricing — Coming Soon"** with a visible banner stating that no payment is
taken, no plan is enforced, and features marked as planned are not implemented.

### 19. Invented testimonials

Three fictional worker quotes with invented names and star ratings. Replaced with
three statements about the platform that are true and checkable.

## Bugs found by running the tests

### 20. Recommendations with no explanation

A job could collect points from freshness or a non-zero wage and be recommended
with **no reason text at all**. `RecommendationService.cs` now skips any job
whose score cannot be explained.

### 21. A shortlisted applicant could never be hired

**Shortlisting someone removed every action button.** Hire and Decline rendered
only while the status was `pending`, although the server permits
`shortlisted → accepted`. Any employer who used the Shortlist button stranded
that applicant permanently. `app.jsx` now offers Hire and Decline for both
states.

### 22. Two informational banners were invisible

`.form-msg` is `display:none` until `.error` or `.success` is added. Two notices
written without a state class never appeared on screen: the pricing page's "not
yet available" disclaimer and the "complete your profile" prompt in the
recommendations panel. `style.css` gained a visible `.form-msg.info` state.

---

## Interface preservation

Your standing instruction was not to change the interface. The stylesheet and the
compiled bundle were compared class-name by class-name against the original:

- **Stylesheet: 153 → 155 class names. Nothing was removed.** The two additions
  are `.form-msg.info` (the visible notice state, bug 22) and `.stats-note` (the
  demonstration-data note on the homepage, bug 16).
- **Classes used by the UI: 141 → 142.** Two are no longer used — `av` and
  `stars`, both belonging only to the fabricated testimonial block the audit
  required removing. One, `more`, already existed in the stylesheet and is now
  actually used, by the "More Filters" control.
- No existing page, colour, font, layout or component was redesigned. Every new
  feature was added as a new tab in the existing dashboard or a new section on an
  existing page, reusing the existing `dash-panel`, `job-card`, `activity` and
  `form-msg` vocabulary.
