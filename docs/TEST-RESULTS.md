# Test Results

Everything below was executed. Where a test could **not** be executed in the
environment the work was done in, it is marked **NOT RUN** and the exact command
to run it on your own machine is given. Nothing in this file is an estimate.

Raw, unedited output from every run is in `docs/test-evidence/`.

---

## Summary

| Suite | Checks | Passed | Failed | Status | Raw output |
|---|---|---|---|---|---|
| Behavioural API tests (30 areas) | 298 | 298 | 0 | **RUN** | `test-evidence/api.txt` |
| Browser end-to-end tests (real UI, Chromium) | 92 | 92 | 0 | **RUN** | `test-evidence/ui.txt` |
| Browser tests: CV upload, Plans menu by role, emails (sections M–S) | 60 | 60 | 0 | **RUN** | `test-evidence/ui_cv_email.txt` |
| Full-lifecycle script (`test_real_backend.py`) | 112 | 112 | 0 | **RUN against the test double only** | `test-evidence/real_backend_against_mirror.txt` |
| Database upgrade / data preservation | 19 | 19 | 0 | **RUN** | `test-evidence/upgrade.txt` |
| C# structural analysis | 8 | 8 | 0 | **RUN** | `test-evidence/static.txt` |
| Phone layout sweep (every page and dashboard tab, 5 roles, 320/360/390 px) | 153 | 153 | 0 | **RUN** | `test-evidence/phone_layout.txt` |
| **Total executed** | **742** | **742** | **0** | | |
| `dotnet build` (C# compilation) | — | — | — | **NOT RUN here** — you confirmed an earlier version compiles; rebuild after this round | see below |
| The same suites against the **real** ASP.NET backend | — | — | — | **NOT RUN — this is your remaining step** | see below |

**This round (12 November 2026)** added API areas 28 (CV upload, 37 checks),
29 (emails on job posted / applied / shortlisted / accepted / declined /
verified, 23 checks) and 30 (reports by email, 18 checks), the 60 browser
checks in `test_ui_cv_email.py`, and the phone layout sweep in
`test_phone_layout.py`. Every earlier suite was re-run unchanged and still
passes. See `docs/CV-EMAIL-PLANS.md` for what the features do.


---

## The one thing still outstanding, and how to close it

Your supervisor asked for the complete process to be tested **against the actual
ASP.NET Core backend, not just the test environment.** That is right, and I could
not do it here: this machine has no .NET SDK, and the network blocks every route
to one — including NuGet, so the project could not restore packages even if a
compiler appeared.

```
$ which dotnet
dotnet: NOT INSTALLED

$ curl https://builds.dotnet.microsoft.com/...  →  connect_rejected
$ curl https://api.nuget.org/v3/index.json      →  CONNECT tunnel failed, 403
$ apt-get download dotnet-sdk-8.0               →  no such package
```

So I wrote the test for you to run instead. **`docs/test-evidence/test_real_backend.py`
runs the exact chain your supervisor listed, against the real backend, in one
command.**

### Run it

```powershell
# Terminal 1 — the real application
cd backend\DailyWork.Api
dotnet run

# Terminal 2 — the test
pip install requests
python docs\test-evidence\test_real_backend.py
```

It prints 112 checks and a PASS/FAIL summary. **Paste that output into your
report** — it is real evidence, produced by your machine against your backend,
and it is exactly what "tested against the actual backend" means.

Two things worth knowing:

- **It does not touch your data.** Every account, job and project it creates
  carries a unique run tag, and it never deletes anything. You can run it as
  many times as you like. I verified that by running it twice in a row against
  the same live server: 112 passed both times.
- **It has been proven to work**, but against the test double described below —
  not against the real backend. Running it is the step that closes this gap.

If anything fails, send me the output and I will fix the cause.

### What it covers

```
registration → job posting → recommendation → application → hiring
→ work records → completion → payment → worker confirmation → ratings
```

plus admin functions, organization verification and approval, projects,
notifications, reports, job editing, role permissions and the rules that protect
the data (no double applications, no illegal status jumps, no reopening a settled
payment, no reviewing someone you never worked with).

### Also outstanding: compilation

You built the solution in Visual Studio on 10 November 2026 and it compiled —
the build produced `DailyWork.Api.exe` with no errors, and the only problem was
Windows blocking the launcher, since fixed with `<UseAppHost>false</UseAppHost>`.
I am recording that as **your** result rather than mine, because I did not run
it. Changes have been made since, so run `dotnet build` again before the test
above.

---

## 1. Behavioural API tests — 298 checks, RUN

### How the API was tested, stated plainly

With no .NET SDK, the C# controllers could not be started. The rules each
controller enforces were therefore re-implemented as a Python server
(`docs/test-evidence/mirror.py`) exposing the **same routes, request and response
shapes, role checks, state machine and error messages**, written from the C#
source line by line, and serving the **real compiled frontend** from `wwwroot`.

**What this proves:** the rules are correct, complete and consistent.

**What it does not prove:** that the C# compiles, or that EF Core issues the SQL
the controllers expect. That is what `test_real_backend.py` is for.

### Result

```
RESULT: 298 passed, 0 failed
```

| # | Area | Checks |
|---|---|---|
| 1 | User registration and login | 9 |
| 2 | Role-based authorization | 7 |
| 3+4 | Job applications and duplicates | 6 |
| 5 | Job posting and editing | 7 |
| 6+7 | Hiring, rejection and work completion rules | 14 |
| 8+9 | Payment creation and duplicate protection | 17 |
| 10+11 | Ratings and rating authorization | 10 |
| 12 | Notifications | 7 |
| 13 | Worker profiles | 9 |
| 14 | Job recommendations | 10 |
| 15 | Organization verification | 13 |
| 16 | Search and filtering | 14 |
| 17 | Administrator functionality | 11 |
| 18 | Database integrity — deletion must not destroy records | 9 |
| 19 | Security and privacy | 7 |
| 20 | Invalid requests and error handling | 7 |
| 21 | Reports | 11 |
| 22 | Homepage statistics are honest | 3 |
| **23** | **Work records after completion** (supervisor issue 1) | **7** |
| **24** | **Worker-submitted work needs approval** (optional improvement) | **9** |
| **25** | **Part-payment confirmation** (supervisor issue 2) | **11** |
| **26** | **Job editing** (supervisor issue 3) | **5** |
| **27** | **Organization projects** (supervisor issue 4) | **17** |
| **28** | **CV upload, download, access rules** | **37** |
| **29** | **Emails: job posted, applied, shortlisted, accepted, declined, verified** | **23** |
| **30** | **Reports by email** | **18** |
| | **Total** | **298** |

Reproduce:

```powershell
cd docs\test-evidence
python mirror.py ..\..\backend\DailyWork.Api\wwwroot
# second terminal:
python test_api.py
```

(Needs `pip install flask bcrypt pyjwt requests`.)

---

## 2. Browser end-to-end tests — 92 checks, RUN

These drive the **actual React application** — the real compiled
`wwwroot/assets/app.js` and `style.css` — in Chromium, clicking what a person
clicks.

```
RESULT: ALL UI CHECKS PASSED
  404s  : none
  errors: none (only expected rejections)
```

| Section | Checks |
|---|---|
| A. Public site and honest content | 7 |
| B. Employer posts a job | 4 |
| C. Worker finds and applies (recommendations, filters, details page) | 13 |
| D. Employer hires, records work, verifies | 5 |
| E. Payment recorded and confirmed | 8 |
| F. Worker sees everything (payments, notifications, reviews, reports) | 14 |
| G. Admin: verification, categories, messages, reports | 9 |
| **I. Editing a job** (supervisor issue 3) | **7** |
| **J. Worker timesheets and approval** (optional improvement) | **3** |
| **K. Part-payment confirmation** (supervisor issue 2) | **7** |
| **L. Organization projects** (supervisor issue 4) | **12** |
| H. Responsive layout (390px, 820px, 1440px) | 3 |
| | **92** |

26 screenshots from this run: `docs/test-evidence/screens/`.

Reproduce:

```powershell
pip install playwright
python -m playwright install chromium
cd docs\test-evidence
python mirror.py ..\..\backend\DailyWork.Api\wwwroot
# second terminal:
python test_ui.py
```

To run it against the **real** backend instead, start `dotnet run` and change the
`U` variable at the top of `test_ui.py` to your running URL.

---

## 3. Database upgrade tests — 19 checks, RUN

The riskiest change, so this is the one area where **real SQLite databases** were
used. A replica of the old schema was built with real rows in it, and the
**actual SQL** from `DatabaseBootstrapper.cs` was executed against it.

```
RESULT: ALL DATABASE UPGRADE CHECKS PASSED
```

```
PASS  no rows lost  -> {'Users': 2, 'Jobs': 2, 'Applications': 1, 'Payments': 2,
                        'Ratings': 1, 'Notifications': 0}  (unchanged)
PASS  all 45 new columns added
PASS  all new tables created
PASS  whole-rupee wage converted exactly   -> Pay=320000 (expected 320000)
PASS  fractional wage converted exactly    -> Pay=153745 (expected 153745)
PASS  second run applies no changes        -> 0 change(s)
PASS  money NOT multiplied a second time   -> Pay=320000
PASS  fresh database is never rescaled     -> Pay=250000
PASS  restart after fresh install leaves money alone -> Pay=250000
```

Reproduce:

```powershell
cd docs\test-evidence
python test_upgrade.py ..\..\backend\DailyWork.Api\Data\DatabaseBootstrapper.cs
```

---

## 4. C# structural analysis — 8 checks, RUN

Not a compiler. A checker that reads all 37 C# files and verifies what a compiler
would catch first.

```
checking 37 C# files

  PASS  all files have balanced delimiters
  PASS  every DailyWork using resolves
  PASS  no controller sets a DTO property that does not exist
  PASS  every injected service is registered
  PASS  every DbSet maps to a model file
  PASS  configured properties exist on their models
  PASS  controllers are well formed
  PASS  no JWT secret committed in appsettings.json

RESULT: ALL STRUCTURAL CHECKS PASSED
```

---

## Bugs found by running the tests

Defects found only because the tests were actually executed are listed here,
because they are the strongest evidence that the testing is real rather than
decorative.

### 12 November 2026 — CV upload, Plans menu, email

| Found by | Bug | Fix |
|---|---|---|
| CV/email browser suite, section S | **On phones the signed-in header was wider than the screen and pushed the ☰ menu button off it.** At 360 px a worker had 53 px of sideways scroll and an administrator 170 px; even visitors had 30 px. This was already present in the version received, not caused by this round. A second cause: dashboard grid columns grew to their widest content instead of the screen. | `style.css`, phones only (below 860 px): compact header buttons, `minmax(0, 1fr)` dashboard columns, and logo-only branding for administrators. Desktop layout unchanged. The new phone sweep finds 0 sideways-scrolling pages out of 153 checked. |
| API suite, area 28 | The test double lost the backslashes in an uploaded file name (`C:\Users\...` arrived as `CUsers...`), because Flask treats them as escape characters. ASP.NET Core does not. A test-double divergence, not a product bug, but it hid whether the path-stripping rule worked. | The mirror now reads the raw `Content-Disposition` header, as ASP.NET does. `CvRules.SafeFileName` was confirmed to handle both `\` and `/`. |
| CV/email browser suite, section P | The test typed into a Location text box on the job form, but Location is a dropdown. A test bug. | The test now chooses from the dropdown. |
| Upgrade suite | The test wrote its database to a hard-coded scratch folder from an earlier session, so it could not run anywhere else. | It now uses the system temp folder, so it runs on Windows too. |

### 10 November 2026 round

| Found by | Bug | Fix |
|---|---|---|
| Upgrade suite, idempotency check | **A newly created `WorkRecords` table was missing its newest columns until the application was restarted a second time** — and would be queried in between with those columns absent. Columns were added *before* tables were created, so a table created by the same run never got them. | `DatabaseBootstrapper.cs`: tables are now created before columns are added, and the `WorkRecords` DDL declares every column. |
| `test_real_backend.py`, section 5 | `GET /api/recommendations` carried a bare `[Authorize]`, so an **employer or administrator could request worker job recommendations** and receive a meaningless list. A role-permission gap of exactly the kind called out in the feedback. | `RecommendationsController.cs`: `[Authorize(Roles = "worker")]`. |
| API suite, section 26 | The mirror accepted `workersNeeded: 0` on a job with someone already hired, because of an `or 1` default that the C# does not have. A test-double divergence, not a product bug — but it would have hidden the real rule. | Test double corrected to compare the raw value, as the C# does. |
| Static analysis, after the DTO changes | `EmployerPaymentDto` was missing `ConfirmedAmount` and `AwaitingConfirmation`, so the employer's payment list would not have compiled. | Fields added to the DTO. |

### Earlier round, kept for the record

| Found by | Bug | Fix |
|---|---|---|
| API suite, check 14 | A job could be recommended **with no reason text at all**. | A job is skipped unless its score can be explained. |
| Browser suite, section D | **A shortlisted applicant could never be hired** — Hire and Decline rendered only while `pending`. | Both actions now render for `pending` and `shortlisted`. |
| Browser suite, section A | The pricing page's "not yet available" disclaimer was **invisible** (`.form-msg` is `display:none` without a state class). The same bug hid the "complete your profile" prompt. | Added a visible `.form-msg.info` state. |
| Browser suite, section A | `isDemoData` flipped to false after one real registration while the counters still included 17 seeded accounts. | The flag stays true while any demonstration record remains, and the count is shown. |

I also improved the structural checker itself: it was attributing the properties
of a nested object initialiser to the outer type, which produced four false
alarms. After fixing it I re-verified that it still catches a genuine error by
injecting one — it did.

---

## What is still untested

- **The real backend.** The headline item above. Until `test_real_backend.py`
  runs green against `dotnet run`, the C# is verified by rules and structure, not
  by execution.
- **Concurrency.** Payment and status writes are wrapped in transactions and the
  state machine rejects illegal transitions, but two employers clicking at the
  same instant was not simulated.
- **Load.** No performance testing. Fine for a demonstration; unmeasured beyond.
- **Real email delivery through a mail server.** Every email was tested in
  outbox mode: the tests read the saved messages and check recipient, subject,
  content and attachments, byte for byte for the CV. Sending through a real SMTP
  server (Gmail, Outlook, SendGrid) was **not run**, because the network here
  blocks outside servers. To check it, set the `Smtp__...` variables as in
  `docs/CV-EMAIL-PLANS.md`, register an account with your own address, and apply
  for a job.
- **Browsers other than Chromium.** Layout was checked at phone, tablet and
  desktop widths, but not in Firefox or Safari.
