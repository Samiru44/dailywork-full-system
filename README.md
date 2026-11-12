# DailyWork — Full System

**Job Matching and Payment Tracking System for Daily Wage Workers in Sri Lanka**

A complete three-tier web application: an ASP.NET Core Web API over a relational
database, serving a React single-page website.

| Tier | Technology |
|---|---|
| **Presentation** | React 18, HTML5, CSS3, JavaScript |
| **Application** | C# / ASP.NET Core 8 Web API, JWT authentication, BCrypt password hashing |
| **Data** | Entity Framework Core 8 over SQLite (one-line switch to SQL Server) |

The website is served by the API itself from `wwwroot`, so the whole system runs
as a single process on a single port.

---

## Start here

| If you want to… | Read |
|---|---|
| Install and run it on Windows | **`HOW-TO-RUN.md`** |
| Know what was fixed and which files changed | **`docs/CHANGELOG-AUDIT.md`** |
| Set up CV upload, the Plans menu and **email** | **`docs/CV-EMAIL-PLANS.md`** |
| Check a proposal requirement against the code | **`docs/FEATURE-CHECKLIST.md`** |
| See what was tested, and what was not | **`docs/TEST-RESULTS.md`** |
| Upgrade an existing database safely | **`docs/DATABASE.md`** |
| Trace a requirement to its implementation | **`docs/TRACEABILITY-MATRIX.md`** |

**Before anything else, run `dotnet build`, then run the end-to-end test against
your own running backend:**

```powershell
cd backend\DailyWork.Api
dotnet run
# then, in a second terminal, from the project root:
python docs\test-evidence\test_real_backend.py
```

That script runs the complete process — registration, posting, recommendation,
application, hiring, work records, completion, payment, worker confirmation,
ratings, plus admin, organization approval, projects and reports — as 112 checks
against the real API. It creates uniquely tagged data and deletes nothing, so it
is safe to run repeatedly.

742 checks were executed here with 0 failures, but **not against the real
backend**: this machine has no .NET SDK and the network blocks every route to
one. `docs/TEST-RESULTS.md` is explicit about what was run and what was not.

> If Visual Studio says **"An Application Control policy has blocked this file"**,
> the code built correctly and Windows is blocking the *launcher*, not your code.
> The project sets `<UseAppHost>false</UseAppHost>` to avoid this. See the
> Troubleshooting section of `HOW-TO-RUN.md`.

---

## Project Structure

```
DailyWork-FullSystem/
│
├── START-DAILYWORK.bat        ← double-click to run (Windows)
├── start-dailywork.sh         ← same, for Mac/Linux
├── DailyWork.sln              ← open in Visual Studio
├── HOW-TO-RUN.md              ← setup instructions
├── TESTING-EVIDENCE.md        ← manual test plan
├── build-frontend.js          ← compiles app.jsx when you change the website
│
├── docs/
│   ├── CHANGELOG-AUDIT.md     every changed file, every bug fixed
│   ├── FEATURE-CHECKLIST.md   each proposal requirement and its status
│   ├── TEST-RESULTS.md        what was tested, what was not, with raw output
│   ├── DATABASE.md            schema, money-as-cents, migration instructions
│   ├── TRACEABILITY-MATRIX.md requirement → implementation → files
│   ├── FLOWCHARTS.html        system flow charts (print to PDF for the report)
│   ├── screenshots/           interface screenshots for the report
│   └── test-evidence/         raw test output, the test scripts, 26 screenshots
│       └── test_real_backend.py  run this against your own `dotnet run`
│
├── backend/DailyWork.Api/
│   ├── Program.cs             startup, DI, JWT + security stamp, DB bootstrap
│   ├── appsettings.json       connection string — no JWT key, deliberately
│   │
│   ├── Models/                EF Core entities
│   │   ├── User.cs            4 roles, account state, profile, verification
│   │   ├── Job.cs             district, required skills, positions, duration
│   │   ├── JobApplication.cs  status + the permitted transitions
│   │   ├── Payment.cs         agreed rate, units, part payments, confirmation
│   │   ├── PaymentAudit.cs    append-only payment history
│   │   ├── WorkRecord.cs      days or shifts actually worked
│   │   ├── JobCategory.cs     categories as data
│   │   ├── ContactMessage.cs  contact form submissions
│   │   ├── Project.cs         an organization's project
│   │   ├── Rating.cs          two-way reviews
│   │   └── Notification.cs    in-app alerts
│   │
│   ├── Data/
│   │   ├── AppDbContext.cs            relationships, indexes, money converter
│   │   ├── DatabaseBootstrapper.cs    upgrades an existing database in place
│   │   └── DbSeeder.cs                admin + demo users + 12 jobs + categories
│   │
│   ├── Dtos/Dtos.cs           request/response contracts with validation
│   ├── Services/
│   │   ├── TokenService.cs            issues the signed JWT, resolves the key
│   │   ├── RecommendationService.cs   the matching rules and their reasons
│   │   ├── PasswordPolicy.cs          password strength
│   │   └── LoginThrottle.cs           failed-login lockout
│   │
│   ├── Controllers/
│   │   ├── AuthController.cs             register, login, throttling
│   │   ├── JobsController.cs             search, filter, sort, view, post, close
│   │   ├── ApplicationsController.cs     apply, shortlist, hire, work, complete
│   │   ├── PaymentsController.cs         part payments, confirm, dispute, audit
│   │   ├── RecommendationsController.cs  scored job matches with reasons
│   │   ├── ReportsController.cs          worker/employer/admin reports + CSV
│   │   ├── OrganizationController.cs     details and verification requests
│   │   ├── CategoriesController.cs       job category management
│   │   ├── ContactController.cs          contact form, honeypot, rate limit
│   │   ├── ProjectsController.cs         organization projects + recruitment tracking
│   │   ├── EmployerController.cs         employer workspace
│   │   ├── RatingsController.cs          two-way reviews, strictly authorised
│   │   ├── NotificationsController.cs    in-app alerts
│   │   ├── ProfileController.cs          view and edit profile
│   │   ├── StatsController.cs            public counters, honestly labelled
│   │   └── AdminController.cs            users, verification queue, messages
│   │
│   └── wwwroot/               the website, served by the API
│       ├── index.html
│       └── assets/            app.js, style.css, React, Font Awesome
│
└── frontend-src/              readable source of the website
    ├── app.jsx                all React components
    └── style.css
```

---

## Database Design

Nine tables with enforced referential integrity:

```
Users ──────< Jobs ──────< Applications >────── Users
  │                             │                 (worker)
  │                             ├──< WorkRecords
  │                             │
  └────────< Payments >─────────┘
                 └──< PaymentAudits

Users >──── Ratings ────< Users        JobCategories
Users >──── Notifications              ContactMessages
```

| Table | Key columns |
|---|---|
| **Users** | Id, Name, Email *(unique)*, Phone, PasswordHash, Role, IsActive, SecurityStamp, District, Skills, ExperienceYears, Certifications, VerificationStatus, OrganizationName, RegistrationNumber |
| **Jobs** | Id, Title, Category, Location, District, Pay, Per, RequiredSkills, WorkersNeeded, ExpectedUnits, Urgent, Status, EmployerId → Users |
| **Applications** | Id, JobId → Jobs, WorkerId → Users, Status, Message, ShortlistedAt, AcceptedAt, CompletedAt, RejectedAt — *unique (JobId, WorkerId)* |
| **WorkRecords** | Id, ApplicationId → Applications, Units, WorkedOn, Note |
| **Payments** | Id, JobId → Jobs, WorkerId → Users, ApplicationId *(unique)*, AgreedRate, RateUnit, UnitsWorked, Amount, AmountPaid, Method, Status, WorkerConfirmed, WorkerDisputeNote, PaidAt |
| **PaymentAudits** | Id, PaymentId → Payments, Action, Amount, ByUserId, At — *append only* |
| **Ratings** | Id, JobId → Jobs, AuthorId → Users, SubjectId → Users, Stars, Comment — *unique (JobId, AuthorId)* |
| **JobCategories** | Id, Name, Description, Icon, SortOrder, IsActive |
| **ContactMessages** | Id, Name, Email, Subject, Message, Handled, CreatedAt |

Constraints that enforce the business rules at the database level:

- `Users.Email` is **unique** — duplicate registration is impossible
- `(JobId, WorkerId)` on Applications is **unique** — a worker cannot apply twice
- `(JobId, AuthorId)` on Ratings is **unique** — nobody can review the same job twice
- `ApplicationId` on Payments is **unique** — one assignment cannot raise two payments
- Deleting a job **cascades** to its applications and payments
- Worker links are **restricted**, so a worker with history cannot be silently orphaned

**Money is stored as a whole number of cents**, converted on the way in and out by
a value converter in `AppDbContext`. Rs. 2,400.00 is stored as `240000`. This
makes totals exact; floating point would drift. `docs/DATABASE.md` explains the
conversion and the upgrade path for an existing database.

---

## API Reference

### Public

| Method | Endpoint | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/register` | `{name,email,phone,password,role}` | `{id,name,email,role,token}` |
| POST | `/api/auth/login` | `{email,password}` | `{id,name,email,role,token}` |
| GET | `/api/jobs?search=&category=&location=&district=&minPay=&maxPay=&per=&urgentOnly=&verifiedOnly=&sort=&page=` | — | paged jobs + total |
| GET | `/api/jobs/{id}` | — | one job, with employer and verification state |
| GET | `/api/categories` | — | active job categories |
| GET | `/api/stats` | — | real counts, plus `isDemoData` and `demoUserCount` |
| POST | `/api/contact` | `{name,email,subject,message}` | stores a message for the admin |

### Authenticated — send `Authorization: Bearer <token>`

| Method | Endpoint | Body | Who |
|---|---|---|---|
| POST | `/api/applications` | `{jobId,message}` | **worker only**, not their own job, once per job |
| GET | `/api/applications/mine` | — | any signed-in user |
| GET | `/api/applications/job/{jobId}` | — | the job's employer |
| PUT | `/api/applications/{id}/status` | `{status,note}` | the job's employer — valid transitions only |
| POST | `/api/applications/{id}/work` | `{units,workedOn,note}` | the job's employer |
| GET | `/api/applications/{id}/work` | — | either party to that assignment |
| GET | `/api/recommendations?take=` | — | worker — scored jobs with reasons |
| GET | `/api/payments/mine` | — | any signed-in user |
| PUT | `/api/payments/{id}/pay` | `{amount,method,notes}` | the job's employer — part payments allowed |
| PUT | `/api/payments/{id}/confirm` | — | **the worker** — confirms the money arrived |
| PUT | `/api/payments/{id}/dispute` | `{note}` | the worker |
| GET | `/api/payments/{id}/audit` | — | either party — full change history |
| POST | `/api/jobs` | `{title,category,location,pay,requiredSkills,workersNeeded,…}` | employer / organization |
| PUT | `/api/jobs/{id}` | job fields | the job's owner |
| DELETE | `/api/jobs/{id}` | — | the job's owner |
| GET / PUT | `/api/organization` | organization details | organization |
| POST | `/api/organization/verify` | `{registrationNumber,address,notes}` | organization — submits for review |
| GET | `/api/reports/worker` | — | worker — outcomes, earnings, by month |
| GET | `/api/reports/employer` | — | employer — jobs, fill rate, spend |
| GET | `/api/reports/worker/payments.csv` | — | worker — CSV export |
| GET | `/api/reports/employer/payments.csv` | — | employer — CSV export |
| PUT | `/api/applications/work/{recordId}` | `{approve,note}` | the job's employer — accepts or rejects a day the worker submitted |
| GET | `/api/projects` | — | organization — projects with recruitment and cost tracking |
| POST / PUT / DELETE | `/api/projects` | project fields | organization — manage projects |

### Employer workspace — employer / organization only

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/employer/stats` | jobs posted, applicants, amount owed and paid |
| GET | `/api/employer/jobs` | this employer's own postings with applicant counts |
| GET | `/api/employer/applicants` | everyone who applied, with contact details and star rating |
| GET | `/api/employer/payments` | payments owed to workers, outstanding first |

### Profile, ratings and notifications

| Method | Endpoint | Purpose |
|---|---|---|
| GET / PUT | `/api/profile` | view or edit your own profile |
| GET | `/api/profile/{id}` | another user's public profile and record |
| GET | `/api/ratings/mine` | reviews written about you |
| GET | `/api/ratings/user/{userId}` | reviews about another user |
| GET | `/api/ratings/pending` | completed jobs you have not reviewed yet |
| POST | `/api/ratings` | leave a review — **only between two parties who completed the same job, once each** |
| POST | `/api/profile/cv` | **worker** uploads or replaces their CV (`multipart/form-data`, field `file`; PDF/DOC/DOCX, max 2 MB) |
| GET / DELETE | `/api/profile/cv` | worker downloads or removes their own CV |
| GET | `/api/profile/{id}/cv` | download a worker's CV — **only that worker, an admin, or an employer they applied to** |
| POST | `/api/reports/email` | email yourself a report: body `{"report":"worker"}`, `"employer"` or `"admin"` (once a minute) |
| GET | `/api/notifications` | your alerts |
| GET | `/api/notifications/unread-count` | badge count |
| PUT | `/api/notifications/{id}/read` | mark one read |
| PUT | `/api/notifications/read-all` | mark everything read |

### Administrator only

| Method | Endpoint | Body / purpose |
|---|---|---|
| GET | `/api/admin/stats` | platform totals |
| GET | `/api/admin/users` | all users, with their state |
| PUT | `/api/admin/users/{id}/role` | `{role}` — invalidates that user's tokens |
| DELETE | `/api/admin/users/{id}` | **deactivates**, preserving payment history |
| PUT | `/api/admin/users/{id}/reactivate` | restores an account |
| GET | `/api/admin/jobs` | all jobs |
| DELETE | `/api/admin/jobs/{id}` | remove a job |
| GET | `/api/admin/verifications` | the verification queue |
| PUT | `/api/admin/verifications/{userId}` | `{decision,note}` — approve or reject |
| GET | `/api/admin/messages` | contact form inbox |
| PUT | `/api/admin/messages/{id}` | mark a message handled |
| POST | `/api/admin/announce` | `{title,message,role}` — notify users |
| POST / PUT / DELETE | `/api/categories` | manage job categories |
| GET | `/api/reports/admin` | users by role, verification states, totals |
| GET | `/api/reports/admin/users.csv` | CSV export |
| GET | `/api/reports/admin/jobs.csv` | CSV export |

Full interactive documentation is generated at **http://localhost:5000/swagger**
while the system is running.

---

## What each role can do

| | Worker | Employer / Organization | Admin |
|---|---|---|---|
| Search and apply for jobs | yes | — | — |
| Receive job recommendations | yes | — | — |
| Post, edit and close jobs | — | yes | yes |
| Shortlist, hire or decline applicants | — | yes | — |
| Record days worked, verify completed work | — | yes | — |
| Submit their own working days for approval | yes | — | — |
| Approve or reject submitted work days | — | yes | — |
| Projects, with recruitment and cost tracking | — | organization only | — |
| Record payments, in full or in part | — | yes | — |
| Confirm or dispute a payment received | yes | — | — |
| Track own payments and earnings | yes | — | — |
| Leave and receive reviews | yes | yes | — |
| Own reports and CSV export | yes | yes | yes |
| Request organization verification | — | organization only | — |
| In-app notifications | yes | yes | yes |
| Edit profile, skills and availability | yes | yes | yes |
| Manage all users and roles | — | — | yes |
| Approve or reject verification requests | — | — | yes |
| Manage job categories | — | — | yes |
| Read contact messages, send announcements | — | — | yes |
| Moderate any job posting | — | — | yes |

## The payment workflow

This is the part of the system that addresses the research problem directly —
daily wage payments that are currently untracked and disputed. Nothing in this
chain is typed in as a bare figure; each step is derived from the one before it.

1. A worker applies to a job → `Applications` row, status `pending`
2. The employer may **shortlist** → status `shortlisted`
3. The employer **hires** → status `accepted`. A job stops accepting hires once
   it has filled every position it asked for.
4. As the work happens, each day or shift is recorded as a `WorkRecords` row.
   The employer can enter one directly, or the **worker can submit their own**,
   which stays `pending` until the employer approves it. **Only approved days
   count**, so a worker cannot increase what they are owed on their own, and a
   rejected day — which carries a reason the worker sees — never reaches the
   payment.
5. The employer **verifies the work** → status `completed`, and in the same
   database transaction the system raises a `Payments` row for
   **`AgreedRate × total units worked`** — not a figure the employer types.
   If a work record changes *after* completion, the payment does not quietly go
   stale: while nothing has been paid it is **recalculated** and the change is
   written to the audit trail, and once any money has been paid the record is
   **frozen** and the change is refused with an explanation.
6. The employer **records payment**, in full or in part. The outstanding balance
   is shown to both sides until it reaches zero. A payment that has been settled
   in full cannot be reopened, so the real settlement date cannot be overwritten.
7. The worker **confirms the money arrived** — or **disputes** it with a note.
   Confirmation covers an *amount*, not the record as a whole: a worker can
   honestly acknowledge a part payment, and when the employer later pays the
   balance the confirmation re-opens so the worker is asked again. A payment
   settled in two instalments is never shown as fully confirmed when only the
   first instalment was.
8. Every change to a payment appends a row to `PaymentAudits`, which is never
   updated or deleted.

Only once the job is `completed` can either side review the other, and only the
two parties to that job, once each.

Each status change is timestamped separately (`ShortlistedAt`, `AcceptedAt`,
`CompletedAt`, `RejectedAt`), and only the valid transitions are accepted — a
rejected application cannot be moved to completed, and a completed one cannot be
reopened to raise a second payment for the same work.

---

## Security

| Measure | Where |
|---|---|
| Passwords stored as BCrypt hashes, never plain text | `AuthController`, `DbSeeder` |
| Password strength rules, and common passwords rejected | `Services/PasswordPolicy.cs` |
| Failed-login lockout: 5 attempts, then 15 minutes | `Services/LoginThrottle.cs` |
| Signed JWT with role claim, 24-hour expiry | `Services/TokenService.cs` |
| **No signing key in the repository** — environment variable, or a gitignored local file | `TokenService.JwtKey()`, `appsettings.json` |
| Blocking or demoting an account invalidates its existing tokens | security stamp, checked in `Program.cs` |
| Role-based authorisation on every protected route | `[Authorize(Roles = "…")]` attributes |
| Public registration cannot create an administrator | `AuthController.Register` |
| The last administrator cannot be deleted or demoted | `AdminController` |
| Deleting a user deactivates them, preserving payment history | `AdminController` |
| Ownership checks before editing another user's data | Jobs, Applications, Payments controllers |
| Reviews only between two parties who completed the same job | `RatingsController` |
| Only valid application status transitions are accepted | `Models/JobApplication.cs` |
| A settled payment cannot be reopened; every change is audited | `PaymentsController`, `Models/PaymentAudit.cs` |
| Internal errors are logged, not returned to the browser | `Program.cs` |
| Contact form protected by a honeypot field and a rate limit | `ContactController` |
| Model validation on every request body | `Dtos/Dtos.cs` data annotations |

Hiding the Admin button in the browser is only tidiness — the `[Authorize]`
attributes on the server are what actually protect the data.

### The JWT signing key

It is deliberately **not** in `appsettings.json`. On startup the server uses
`DAILYWORK_JWT_KEY` if that environment variable is set; otherwise it generates a
random key once and writes it to `jwt-key.local.txt` beside the executable, which
`.gitignore` excludes. Nothing needs configuring to run the project locally, and
no key ends up committed.

To set one explicitly on Windows:

```powershell
setx DAILYWORK_JWT_KEY "a-long-random-string-of-at-least-32-characters"
```

Then open a new terminal. Changing the key signs everyone out, which is what you
want if a key was ever exposed.

---

## Editing the website

The page is pre-compiled for speed. To change it:

1. Edit `frontend-src/app.jsx` (components) or `frontend-src/style.css` (styling)
2. Re-compile and copy both files across in one step:
   ```
   npm install @babel/standalone
   node build-frontend.js
   ```
3. Refresh the browser with Ctrl+F5. The server does not need restarting.

`build-frontend.js` writes `wwwroot/assets/app.js` and copies the stylesheet. If
the JSX has a syntax error it prints the line and column and changes nothing.

For small CSS tweaks you can edit `wwwroot/assets/style.css` directly and just
refresh — but remember to put the same change into `frontend-src/style.css`, or
the next build will overwrite it.

All server communication is in one place: the `API` object near the top of
`app.jsx`, which calls the endpoints listed above through a single `http()` helper.

---

## Known limitations

Being specific, so nothing here is mistaken for finished.
`docs/FEATURE-CHECKLIST.md` has the full requirement-by-requirement list.

- **The C# has not been compiled.** Run `dotnet build` first. See
  `docs/TEST-RESULTS.md` for why, and for what *was* tested.
- **Email needs a mail server you configure.** Emails are sent when a job is
  posted, when someone applies, when an application is shortlisted, accepted,
  declined or verified, and when a user asks for a report. Until you set the
  `Smtp__...` variables, each email is saved as an `.eml` file in
  `backend/DailyWork.Api/email-outbox/` instead of sent, and the demo
  `@dailywork.lk` accounts are never really emailed. See
  `docs/CV-EMAIL-PLANS.md`. There is no SMS, the contact form still goes to the
  admin inbox rather than by email, and sign-up has no email verification.
- **The only file upload is the worker's CV.** There are no profile photos, and
  no document uploads for verification. An organization submits its
  registration number and address as text, and the administrator approves on
  that basis.
- **No online payment processing.** This is payment *tracking*, as the proposal
  described. The pricing page says so rather than implying billing works.
- **Multiple logins under one organization account** are not supported — one
  login per organization.
- **Matching is rule-based, not machine learning**, deliberately — so every
  recommendation can state why it was made.
- **EF Core migration files are not included.** The schema upgrade is applied by
  a tested SQL bootstrapper instead; `docs/DATABASE.md` gives the exact
  `dotnet ef` commands to generate real migrations on your machine.
- **SQLite with no load testing.** Fine for a demonstration; unmeasured beyond it.

## Further work

- SMS notifications
- Document upload for organization verification
- Real-time notifications with SignalR
- Online payment gateway integration
- Sinhala and Tamil language support
