# Feature Completion Checklist

Each row is a requirement from your project proposal and interim report. Status
is one of:

- **Done** — implemented and covered by an executed test
- **Partial** — works, but narrower than the proposal described (the gap is stated)
- **Not done** — not implemented (the reason is stated)

Compilation of the C# has **not** been verified — see `TEST-RESULTS.md`. Every
"Done" below means the behaviour was tested through the API or the browser, not
that the project has been built with `dotnet build`.

---

## The four priorities your supervisor named

| # | Priority | Status | Evidence |
|---|---|---|---|
| A | Job recommendation system | **Done** | API area 14 (10 checks); browser section C — recommendations with a match % and a written reason each |
| B | Organization verification | **Done** | API area 15 (13 checks); browser section G — admin approved a pending organization |
| C | Reporting | **Done** | API area 21 (11 checks); browser sections E/F/G — all three report views showed real figures |
| D | Fixing existing workflows | **Done** | Browser sections B–F — the whole lifecycle from posting to confirmed payment, in one run |

## The four issues raised on 10 November 2026

| # | Issue | Status | Evidence |
|---|---|---|---|
| 1 | Work records after completion must not leave the payment wrong | **Done** | API area 23 (7 checks) — recalculated while unpaid, refused once paid |
| 2 | Part-payment confirmation must not survive a later payment | **Done** | API area 25 (11 checks); browser section K (7 checks) |
| 3 | An Edit Job form in the employer dashboard | **Done** | API area 26 (5 checks); browser section I (7 checks) |
| 4 | Organization-specific functionality | **Done** | API area 27 (17 checks); browser section L (12 checks) — projects with recruitment and cost tracking |
| 5 | Test against the real ASP.NET backend | **Your step** | `docs/test-evidence/test_real_backend.py` — written, proven runnable, 112 checks. I could not run it: no .NET SDK here. See `TEST-RESULTS.md`. |
| — | Optional: workers submit their own hours for approval | **Done** | API area 24 (9 checks); browser section J (3 checks) |
| — | Optional: better partial-payment tracking | **Done** | Covered by issue 2 above |
| — | Optional: email notifications | **Done** (12 Nov) | API area 29 (23 checks); browser section P. Sent on job posted, applied, shortlisted, accepted, declined, verified. Real SMTP sending is not run here; see `CV-EMAIL-PLANS.md`. |

## Added on 12 November 2026

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | CV upload in the job seeker's profile (upload, download, replace, remove; PDF/DOC/DOCX up to 2 MB) | **Done** | API area 28 (37 checks); browser sections N, O, R (29 checks) |
| 2 | CV goes to the employer with the application, and only that employer can download it | **Done** | API area 28; browser section O |
| 3 | Payment plan menu shown only to employers and organizations (and to visitors on the public site) | **Done** | Browser section M (14 checks): workers and admins see no Pricing or Plans link |
| 4 | Emails when a job is posted, applied for, shortlisted, accepted, declined or verified | **Done** | API area 29 (23 checks); browser sections O, P |
| 5 | Reports sent by email, with a CSV attached | **Done** | API area 30 (18 checks); browser section Q (8 checks) |
| 6 | Phone layout: no sideways scrolling on any page or dashboard tab | **Done** | `test_phone_layout.py`: 153 page views at 320/360/390 px, 0 overflowing |

Real email delivery through an SMTP server is the one part not run here: the
network blocks outside mail servers. Every email was checked in outbox mode
instead. Setup steps are in `docs/CV-EMAIL-PLANS.md`.

---

## 1. Accounts and roles

| Requirement | Status | Notes |
|---|---|---|
| Worker, Employer, Organization and Admin roles | **Done** | Four roles, each with its own dashboard |
| Registration and login | **Done** | BCrypt hashing, JWT bearer tokens |
| Password strength rules | **Done** | Min 8 chars, letter + digit, rejects common passwords and ones containing your own name or email |
| Protection against password guessing | **Done** | 5 failed attempts locks that email/IP pair for 15 minutes |
| Role-based access to every endpoint | **Done** | 14 API checks; an employer can no longer apply for jobs |
| Blocking an account takes effect immediately | **Done** | Security stamp in the token, re-checked on every request |
| Email verification on sign-up | **Not done** | The system now sends email, but sign-up does not ask the user to confirm their address. |

## 2. Worker profiles

| Requirement | Status | Notes |
|---|---|---|
| Skills | **Done** | Free text, used by the matching rules |
| Location and district | **Done** | District drives matching; location refines it |
| Years of experience and description | **Done** | `ExperienceYears`, `Experience` |
| Certifications | **Done** | `Certifications` |
| Availability toggle | **Done** | Unavailable workers are not matched to new jobs |
| Work history visible on the profile | **Done** | Completed jobs with dates, from real applications |
| Average rating and number of ratings | **Done** | Computed from rating rows, not stored |
| CV upload | **Done** (12 Nov) | PDF/DOC/DOCX up to 2 MB; shared only with employers the worker applies to. API area 28 |
| Profile photo upload | **Not done** | Avatars are generated initials. The CV is the only file upload. |

## 3. Employer and organization management

| Requirement | Status | Notes |
|---|---|---|
| Employer profile and company details | **Done** | Name, phone, district, address |
| Organization registration details | **Done** | Registration number, address, website |
| Submit a verification request | **Done** | `POST /api/organization/verification` |
| Admin reviews, approves or rejects with a note | **Done** | Verification queue in the admin panel |
| Verified badge shown only after approval | **Done** | Gated on `VerificationStatus == "verified"` |
| Employer sees their own recruitment figures | **Done** | Jobs posted, applicants, fill rate, spend |
| Projects: group postings by site, contract or season | **Done** | Organizations only |
| Recruitment tracking per project | **Done** | Positions, applicants, shortlisted, hired, still needed and fill rate, counted from the real applications |
| Cost tracking per project | **Done** | Committed, paid and outstanding against the budget, from the real payments, with an over-budget flag |
| Multiple users under one organization account | **Not done** | One login per organization. Would need an organization-members table; out of scope for this submission. |

## 4. Job posting and management

| Requirement | Status | Notes |
|---|---|---|
| Post a job with title, category, location, wage | **Done** | |
| Wage unit (day / shift / hour / job) | **Done** | `Per` / `RateUnit` |
| Required skills | **Done** | Drives matching |
| Number of workers needed | **Done** | A job stops accepting hires once it is full |
| Expected duration | **Done** | `ExpectedUnits`, start and end dates |
| Mark a job urgent | **Done** | Scores higher in recommendations |
| Close a job | **Done** | |
| Dedicated job details page | **Done** | Wage, positions, skills, employer, verification state |
| Job categories managed as data | **Done** | Admin can add, rename, reorder and deactivate |
| Edit a job after posting | **Done** | Edit button on every open posting in My Jobs; the same form serves posting and editing. The wage is locked once someone is hired, and positions cannot drop below the number hired. |

## 5. Job search, filtering and matching

| Requirement | Status | Notes |
|---|---|---|
| Keyword search | **Done** | Title, description and skills |
| Filter by category | **Done** | |
| Filter by location and district | **Done** | |
| Filter by wage range | **Done** | Minimum and maximum |
| Filter by wage unit | **Done** | |
| Urgent jobs only | **Done** | |
| Verified employers only | **Done** | |
| Sorting (newest, wage high/low) | **Done** | |
| Paging | **Done** | |
| Intelligent recommendations for a worker | **Done** | Skills 40, district 20, category 15, location 10, experience 10, wage 10, urgency 5, freshness 5, normalised to a 0–100 match score |
| Every recommendation explains itself | **Done** | A job with no explainable reason is not shown at all |
| Suggest suitable workers for a new job | **Done** | Used to decide who gets notified |
| Machine-learning based matching | **Not done** | Deliberately rule-based, so the reasons can be shown to the worker and followed by a marker. The proposal's wording ("intelligent matching") is met by explainable rules, not ML. |

## 6. Applications and hiring

| Requirement | Status | Notes |
|---|---|---|
| Worker applies with a note | **Done** | Workers only; not to their own posting; once per job |
| Employer sees applicants with contact details and skills | **Done** | |
| Shortlist | **Done** | And a shortlisted applicant can then be hired — this was broken, see bug 21 |
| Hire | **Done** | Blocked once the job is full |
| Decline with a reason | **Done** | The applicant sees the reason |
| Valid status transitions only | **Done** | 12 API checks against the state machine |
| Worker sees their application status | **Done** | |

## 7. Daily wage and work tracking

| Requirement | Status | Notes |
|---|---|---|
| Record days or shifts actually worked | **Done** | `WorkRecord` rows per assignment |
| Employer verifies work done | **Done** | Moves the application to `completed` |
| Amount owed calculated from work recorded | **Done** | `AgreedRate × total units` — not typed in by the employer |
| Both sides see the breakdown | **Done** | e.g. `3 day(s) at Rs. 2,400` |
| Work changed after completion keeps the payment correct | **Done** | Recalculated while nothing is paid; refused with an explanation once payment has started — never silently ignored. |
| Worker-submitted timesheets | **Done** | A worker can record a day themselves; it stays `pending` until the employer approves it in the Work Approvals tab. Only approved days count towards the payment, and a rejection carries a reason the worker sees. |

## 8. Payment tracking

| Requirement | Status | Notes |
|---|---|---|
| A payment record per completed assignment | **Done** | Raised automatically on verification |
| Record a payment, in full or in part | **Done** | Outstanding balance shown on both sides |
| Payment method | **Done** | Cash, bank transfer, mobile |
| A settled payment cannot be reopened | **Done** | Protects the real settlement date |
| Worker confirms the money arrived | **Done** | Confirmation covers an *amount*, so a part payment can be acknowledged honestly |
| A later payment re-opens confirmation | **Done** | Paying the balance clears the earlier confirmation and asks the worker again, so a two-instalment payment is never shown as fully confirmed when only the first was |
| Worker can dispute a payment with a note | **Done** | |
| Exact money arithmetic | **Done** | Stored as whole cents, not floating point |
| Full audit trail of every change | **Done** | Append-only `PaymentAudit` |
| Status and payment written atomically | **Done** | One database transaction |
| Online payment processing | **Not done** | Out of scope in the proposal too — this is payment *tracking*. The pricing page now says so instead of implying billing works. |

## 9. Ratings and reviews

| Requirement | Status | Notes |
|---|---|---|
| Worker and employer rate each other | **Done** | |
| Only after the work is genuinely completed | **Done** | Both parties must be on that job, with status `completed` |
| One review per person per job | **Done** | Unique database index |
| Average rating on the profile | **Done** | |
| Reviews visible to both sides | **Done** | |

## 10. Notifications

| Requirement | Status | Notes |
|---|---|---|
| Notified when shortlisted, hired or declined | **Done** | |
| Notified when work is verified | **Done** | |
| Notified when a payment is recorded | **Done** | |
| Notified when a review is received | **Done** | |
| Matching workers notified of a new job | **Done** | Uses the matching rules, so only suitable workers are told |
| Unread count and mark-as-read | **Done** | |
| Email notifications | **Done** (12 Nov) | Job posted, applied (with CV for the employer), shortlisted, accepted, declined, verified. API area 29 |
| SMS notifications | **Not done** | Email and in-app only. |

## 11. Reports and analytics

| Requirement | Status | Notes |
|---|---|---|
| Worker report: applications, outcomes, success rate | **Done** | |
| Worker report: earnings, pending wages, by month | **Done** | Verified at Rs. 7,200 against a real lifecycle |
| Employer report: jobs, applicants, fill rate | **Done** | |
| Employer report: spend and outstanding, by month | **Done** | |
| Admin report: users by role, verification states, platform totals | **Done** | |
| CSV export | **Done** | Four exports; admin-only ones refuse non-admins (403) |
| Charts | **Partial** | Simple bar charts drawn in the existing style. No charting library was added, to avoid changing the stack. |
| Emailed reports | **Done** (12 Nov) | **Email me this report** on each Reports tab; CSV attached; once a minute. API area 30 |
| Scheduled reports | **Not done** | Reports are emailed on request, not on a timetable. |

## 12. Administration

| Requirement | Status | Notes |
|---|---|---|
| View and manage users | **Done** | |
| Deactivate an account without destroying history | **Done** | Soft delete; payments and ratings survive |
| Verification queue | **Done** | |
| Job category management | **Done** | |
| Contact message inbox | **Done** | |
| Platform announcements | **Done** | |
| Admin cannot deactivate themselves | **Done** | |

## 13. Website and honesty

| Requirement | Status | Notes |
|---|---|---|
| Homepage statistics are real database counts | **Done** | Floors removed; a note says how many counted accounts are demonstration samples |
| Contact form actually stores the message | **Done** | Success shown only after the server accepts; honeypot and rate limit |
| No fabricated testimonials | **Done** | Replaced with checkable statements |
| Pricing page does not imply billing works | **Done** | "Coming Soon", with a visible not-available banner |
| Admin credentials not shown publicly | **Done** | |
| Light and dark mode | **Done** | Unchanged from your version |
| Responsive layout | **Done** | Checked at 390px, 820px and 1440px with no horizontal overflow |

## 14. Database and deployment

| Requirement | Status | Notes |
|---|---|---|
| Existing databases upgrade without losing data | **Done** | 19 executed checks against real SQLite files; see `DATABASE.md` |
| The upgrade is safe to run twice | **Done** | Idempotent, with a marker table |
| No secrets in the repository | **Done** | JWT key from environment or a gitignored local file |
| EF Core migrations | **Partial** | The schema upgrade is applied by `DatabaseBootstrapper.cs` because no .NET SDK was available to scaffold and compile a migration. `DATABASE.md` gives the exact `dotnet ef` commands to generate proper migrations on your machine, which is the better long-term route. |

---

## Everything not done, in one list

So this is in one place and nothing is buried:

1. Email verification on sign-up
2. SMS notifications. Email notifications are done.
3. *Scheduled* reports. Reports can be emailed on request; they are not sent automatically on a timetable.
4. Profile photo upload, and document upload for verification. CV upload is the only file upload.
5. Multiple user logins under one organization account
6. Machine-learning matching — deliberately explainable rules instead
7. Online payment processing — out of scope; this is payment *tracking*
8. Charting library — simple bars in the existing style, to avoid changing the stack
9. EF Core migration files — a tested SQL upgrader instead, with the commands to generate migrations yourself

Items from earlier versions of this list that are now **done**: editing a job
after posting, worker-submitted timesheets, email notifications, emailed
reports, and CV upload.

And one item is not mine to close: **running the suites against the real ASP.NET
backend.** The script is written and proven runnable
(`docs/test-evidence/test_real_backend.py`, 112 checks); this machine has no .NET
SDK and the network blocks every route to one, including NuGet. `TEST-RESULTS.md`
gives the two commands.
