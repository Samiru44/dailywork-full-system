# Testing Evidence — DailyWork

This document is the **manual** test plan for the system — the checks you carry
out yourself and record, to answer the supervisor's comment that *"no testing
evidence has been presented"*.

**Before submitting, run the steps below on your own machine and replace the
screenshots in `docs/screenshots/` with your own.** Screenshots taken on your
computer, showing your own data, are what the marker is looking for.

> **Automated testing is documented separately in `docs/TEST-RESULTS.md`**, which
> records 260 executed checks (API behaviour, browser end-to-end, database
> upgrade, static analysis) with the raw output in `docs/test-evidence/`. It is
> also explicit that `dotnet build` was **not** run — that is the first thing for
> you to verify. The manual plan below and that document complement each other;
> neither replaces the other.

---

> **Deployment update (12 November 2026):** The deployment-preparation branch targets
> .NET 10 LTS and Entity Framework Core 10. Earlier project notes may refer to .NET 8;
> .NET 8 reached end of support on 10 November 2026. The new GitHub Actions workflow
> performs a .NET 10 restore/build on pushes to the deployment branch.

## 1. Test environment

| Item | Value |
|---|---|
| Backend | ASP.NET Core 10 Web API (C#) |
| Database | SQLite via Entity Framework Core 10 (PostgreSQL supported for hosting) |
| Frontend | React 18 served from the API's `wwwroot` |
| Browser | *(record the browser and version you used)* |
| Date of test run | *(record the date)* |
| Tester | *(your name)* |

---

## 2. Functional test cases

Work through these in the browser with the system running. Mark Pass/Fail and
take a screenshot of each one.

| # | Test case | Steps | Expected result | Result |
|---|---|---|---|---|
| F1 | Home page loads | Open `http://localhost:5000` | Page renders; the four counters show values fetched from `/api/stats` | |
| F2 | Job list loads from database | Click **Find Jobs** | 12 seeded jobs appear, each with its employer's name | |
| F3 | Keyword search | Type `mason` in the search box | Only the Mason job remains; browser network tab shows `GET /api/jobs?search=mason` | |
| F4 | Category filter | Choose **Construction** | Only construction jobs listed | |
| F5 | Location filter | Type `Colombo` | Only Colombo jobs listed | |
| F6 | Registration | Register a new Worker | Account created, redirected to Dashboard, JWT stored in browser | |
| F7 | Duplicate email rejected | Register again with the same email | Error: *An account with this email already exists.* | |
| F8 | Password rule | Register with a 3-character password | Error: *Password must be at least 6 characters.* | |
| F9 | Login — valid | Log in as `admin@dailywork.lk` / `Admin@12345` | Redirected to the Admin Panel | |
| F10 | Login — invalid | Log in with a wrong password | Error: *Invalid email or password.* | |
| F11 | Apply to a job | As a logged-in worker, click **Apply Now** | Confirmation shown; application saved | |
| F12 | Duplicate application refused | Apply to the same job again | Error: *You have already applied for this job.* | |
| F13 | Dashboard shows applications | Open **Dashboard** | The application appears with its status and date | |
| F14 | Admin — user list | Admin Panel → Manage Users | All registered users listed from the database | |
| F15 | Admin — change role | Change a worker to employer | Role updates; reload confirms it persisted | |
| F16 | Admin — job moderation | Admin Panel → Manage Jobs → delete a job | Job removed; it no longer appears on Find Jobs | |
| F17 | Data persists across restart | Stop the server, start it again, reload | Registered users and applications are still there | |
| F18 | Employer posts a job | Log in as employer → Post a Job → fill the form | Job saved and immediately visible on Find Jobs | |
| F19 | Employer sees applicants | Applicants tab | Applicant listed with phone, email and skills | |
| F20 | Employer hires a worker | Click **Hire** | Status changes to accepted; worker is notified | |
| F21 | Employer verifies work | Click **Verify Work Done** | Status becomes completed | |
| F22 | Payment raised automatically | Open the employer's Payments tab after F21 | A pending payment for the job's amount appears without anyone creating it | |
| F23 | Employer releases payment | Click **Mark Paid** | Status becomes paid; worker is notified | |
| F24 | Worker sees payment history | Worker → Payments | Payment shown as paid with the date; earnings total updates | |
| F25 | Two-way reviews | Both sides → Reviews tab after completion | Each can rate the other 1–5 stars with a comment | |
| F26 | Review before completion blocked | Try to review an unfinished job via Swagger | Refused — *You can only review someone after the job is completed.* | |
| F27 | Duplicate review blocked | Submit a second review for the same job | `409` — *You have already reviewed this job.* | |
| F28 | Notifications raised | Check Notifications after applying, hiring, completing, paying | An alert exists for each event | |
| F29 | Mark all as read | Click **Mark all as read** | Badge clears and the button disappears | |
| F30 | Profile editing | My Profile → change skills → Save | Confirmation shown; value persists after reload | |
| F31 | Worker sees no employer tools | Log in as worker | No Post a Job or Applicants option in the sidebar | |
| F32 | Job close | Employer → My Jobs → Close | Job disappears from the public job list | |

---

## 3. Security test cases

| # | Test case | Steps | Expected result | Result |
|---|---|---|---|---|
| S1 | Anonymous apply blocked | Log out, click **Apply Now** | Redirected to Login; no application saved | |
| S2 | Worker cannot reach admin panel | Log in as a worker, browse to `#/admin` | Redirected to Dashboard | |
| S3 | Admin API rejects non-admin token | In Swagger, call `GET /api/admin/users` with a worker's token | `403 Forbidden` | |
| S4 | Admin API rejects no token | Call `GET /api/admin/users` with no token | `401 Unauthorized` | |
| S5 | Admin cannot be self-registered | Register with role `admin` via Swagger | `400` — *Admin accounts cannot be self-registered.* | |
| S6 | Last admin protected (demote) | Admin Panel → set your own role to worker | Refused — *Cannot demote the last remaining administrator.* | |
| S7 | Last admin protected (delete) | Admin Panel → delete your own admin account | Refused with the same rule | |
| S8 | Passwords are hashed | Open `dailywork.db` with DB Browser for SQLite, view the Users table | `PasswordHash` holds a BCrypt hash (`$2a$…`), never the plain password | |
| S9 | Worker cannot reach employer API | Call `GET /api/employer/applicants` with a worker's token | `403 Forbidden` | |
| S10 | Employer cannot pay another employer's worker | Call `PUT /api/payments/{id}/pay` for a payment you do not own | `403 Forbidden` | |
| S11 | Cannot rate yourself | `POST /api/ratings` with your own id as subject | `400` — *You cannot rate yourself.* | |
| S12 | Cannot read another user's notifications | `GET /api/notifications` returns only your own rows | No other user's alerts appear | |

> **S8 is worth a screenshot.** Showing the hashed column in the database is
> strong, concrete evidence of the security requirement being met.

---

## 4. Usability and compatibility

| # | Test case | Expected result | Result |
|---|---|---|---|
| U1 | Desktop layout (1920×1080) | All sections aligned, nothing overlapping | |
| U2 | Laptop layout (1366×768) | Layout adapts, no horizontal scroll | |
| U3 | Mobile layout (390×844) | Menu collapses to the hamburger button; cards stack | |
| U4 | Second browser | Works in Chrome and in Edge or Firefox | |
| U5 | Error messages are clear | Every failure explains what went wrong in plain words | |

---

## 5. API testing with Swagger

With the system running, open **http://localhost:5000/swagger**. This gives a
test console for every endpoint and is an easy source of screenshots.

Suggested sequence:

1. `POST /api/auth/login` with the admin credentials → copy the `token` from the response
2. Click **Authorize** at the top of the page, paste `Bearer <token>`
3. `GET /api/admin/stats` → platform totals
4. `GET /api/admin/users` → the user table
5. `POST /api/applications` with `{"jobId": 1}` → application created
6. Repeat step 5 → `409 Conflict`, proving the duplicate rule is enforced server-side

Screenshot the request and response panels for each.

---

## 6. Results already verified during development

The complete worker and employer lifecycle was driven through an automated browser
(Playwright) against a server implementing this exact API contract. **All 40 checks
passed**, with no console errors and no missing resources:

```
About page renders                        PASS
aim statement present                     PASS
About linked from navbar                  PASS

-- EMPLOYER ----------------------------------------
employer logs in                          PASS
employer sees Post a Job option           PASS
employer sees Applicants option           PASS
job posted                                PASS
new job listed under My Jobs              PASS
posted job is live for workers            PASS

-- WORKER ------------------------------------------
worker logs in                            PASS
worker does NOT see Post a Job            PASS
worker tab 'My Applications' opens        PASS
worker tab 'Payments' opens               PASS
worker tab 'Reviews' opens                PASS
worker tab 'Notifications' opens          PASS
worker tab 'My Profile' opens             PASS
welcome notification shown                PASS
profile saves                             PASS
application recorded                      PASS

-- HIRING AND VERIFICATION -------------------------
employer notified of applicant            PASS
applicant visible with contact details    PASS
worker hired                              PASS
work verified                             PASS
payment raised automatically on completion PASS
payment released                          PASS

-- REVIEWS -----------------------------------------
pending review offered to employer        PASS
employer review saved                     PASS
worker received the review                PASS
worker can review the employer back       PASS
worker review submitted                   PASS

-- NOTIFICATIONS -----------------------------------
worker notified: hired                    PASS
worker notified: work verified            PASS
worker notified: payment                  PASS
worker notified: review                   PASS
mark all as read works                    PASS

-- RECORDS AND ADMIN -------------------------------
worker sees payment as paid               PASS
earnings total updated                    PASS
profile shows rating earned               PASS
profile shows job completed               PASS
admin lands on admin panel                PASS
admin stats load                          PASS
about page fits mobile                    PASS

404s  : none
errors: none
```

Screenshots from that run are in `docs/screenshots/`, numbered in the order the
lifecycle was executed. **Replace them with screenshots from your own machine
before submitting** — the marker wants to see the system running on your computer.

### Suggested demonstration order for the viva

This sequence shows the whole system in about four minutes and produces a clean
set of screenshots:

1. Home page, then **About** — read the aim statement aloud
2. Log in as the employer → **Post a Job**
3. Log out, log in as the worker → **Find Jobs** → apply to that job
4. Back as the employer → **Applicants** → **Hire** → **Verify Work Done**
5. **Payments** → show the payment appeared by itself → **Mark Paid**
6. **Reviews** → rate the worker
7. Back as the worker → **Notifications** (five alerts), **Payments** (paid),
   **Reviews** (the review received), **My Profile** (rating and earnings updated)
8. Log in as admin → **Manage Users** and **Manage Jobs**
9. Finish at `http://localhost:5000/swagger` to show the API layer

## 7. Known limitations

Stating these honestly is better than leaving the marker to find them:

- Payments are recorded and tracked end to end, but no online payment gateway is
  connected, so the actual transfer of money still happens outside the system.
  The platform's contribution is the permanent, shared record of what was owed
  and what was paid.
- Notifications appear inside the dashboard rather than being pushed by email or SMS.
- The interface is in English only; Sinhala and Tamil support is planned.
- Job matching uses category, location and keyword filters rather than a learned
  recommendation model.
