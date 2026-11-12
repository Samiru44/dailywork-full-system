"""
End-to-end test against the REAL ASP.NET Core backend.

This is the test the supervisor asked for: the complete process, run against
the actual C# API and the actual SQLite database rather than a test double.

    Registration -> Job Posting -> Recommendation -> Application -> Hiring
    -> Work Records -> Completion -> Payment -> Worker Confirmation -> Ratings

plus admin functions, organization approval, projects, notifications and
reports.

------------------------------------------------------------------------
HOW TO RUN IT
------------------------------------------------------------------------
1. Start the application and leave it running:

       cd backend\\DailyWork.Api
       dotnet run

2. In a SECOND terminal, from the project root:

       pip install requests
       python docs\\test-evidence\\test_real_backend.py

   Against a different address:

       python docs\\test-evidence\\test_real_backend.py http://localhost:5001

Every account, job and project it creates carries a unique tag, so it can be
run as many times as you like without clashing with earlier runs or with data
already in your database. It never deletes anything.

It needs the seeded administrator (admin@dailywork.lk / Admin@12345) to test
the admin functions. If that account's password has been changed, set it:

       set DW_ADMIN_PASSWORD=your-password          (Windows)
       export DW_ADMIN_PASSWORD=your-password       (Mac/Linux)

The last line printed is the result. Copy the whole output into your report:
it is real evidence, produced by your own machine against your own backend.
"""

import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("This script needs the requests library.\n\n    pip install requests\n")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/") + "/api"
ADMIN_EMAIL = "admin@dailywork.lk"
ADMIN_PASSWORD = os.environ.get("DW_ADMIN_PASSWORD", "Admin@12345")

# Everything this run creates carries this tag, so repeated runs never collide.
TAG = time.strftime("%m%d%H%M%S")
PW = "Secret@123"

passed, failed, skipped = [], [], []


def check(label, ok, detail=""):
    mark = "  PASS  " if ok else "  FAIL  "
    print(mark + label + (("  ->  " + str(detail)[:95]) if detail else ""))
    (passed if ok else failed).append(label)


def skip(label, why):
    print("  SKIP  " + label + "  ->  " + why)
    skipped.append(label)


def req(method, path, body=None, token=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        return requests.request(method, BASE + path, json=body, headers=headers, timeout=30)
    except requests.exceptions.ConnectionError:
        sys.exit(
            "\nCould not reach " + BASE + "\n\n"
            "Start the backend first, in its own terminal:\n\n"
            "    cd backend\\DailyWork.Api\n"
            "    dotnet run\n")


def post(p, b=None, t=None):   return req("POST", p, b, t)
def put(p, b=None, t=None):    return req("PUT", p, b or {}, t)
def get(p, t=None):            return req("GET", p, None, t)
def delete(p, t=None):         return req("DELETE", p, None, t)


_accounts = [0]


def register(name, role):
    """Creates one account for this run and returns its token, id and email."""
    _accounts[0] += 1
    n = _accounts[0]
    email = f"{role}{n}.{TAG}@dwtest.lk"
    phone = f"07{TAG[-7:]}{n}"
    r = post("/auth/register", {"name": f"{name} {TAG}", "email": email,
                                "phone": phone, "password": PW, "role": role})
    if not r.ok:
        sys.exit(f"\nCould not register the {role} test account: {r.status_code} {r.text[:200]}\n")
    d = r.json()
    return d["token"], d["id"], email


def find(rows, title_key, title):
    return [x for x in rows if x.get(title_key) == title]


print("=" * 74)
print("DAILYWORK — END-TO-END TEST AGAINST THE REAL ASP.NET CORE BACKEND")
print("=" * 74)
print(f"  Target : {BASE}")
print(f"  Run tag: {TAG}   (everything created by this run is tagged with it)")
print("=" * 74)

# ---------------------------------------------------------------------
print("\n1. THE SERVER IS RUNNING AND SERVING REAL DATA")
# ---------------------------------------------------------------------
st = get("/stats")
check("the API responds", st.status_code == 200, st.status_code)
stats = st.json()
check("homepage statistics come from the database",
      "isDemoData" in stats and "workers" in stats,
      f"workers={stats.get('workers')} demo={stats.get('isDemoData')}")

# ---------------------------------------------------------------------
print("\n2. REGISTRATION")
# ---------------------------------------------------------------------
worker_t, worker_id, worker_email = register("E2E Worker", "worker")
emp_t, emp_id, emp_email = register("E2E Employer", "employer")
org_t, org_id, org_email = register("E2E Organization", "organization")
check("a worker can register", bool(worker_t))
check("an employer can register", bool(emp_t))
check("an organization can register", bool(org_t))

weak = post("/auth/register", {"name": "Weak", "email": f"weak.{TAG}@dwtest.lk",
                               "phone": "0770000000", "password": "123", "role": "worker"})
check("a weak password is refused", weak.status_code == 400,
      weak.json().get("message", "")[:70] if weak.content else weak.status_code)

check("logging in returns a token",
      post("/auth/login", {"email": worker_email, "password": PW}).status_code == 200)
check("a wrong password is refused",
      post("/auth/login", {"email": worker_email, "password": "WrongPass@1"}).status_code
      in (400, 401))

# ---------------------------------------------------------------------
print("\n3. WORKER PROFILE")
# ---------------------------------------------------------------------
pr = put("/profile", {"name": f"E2E Worker {TAG}", "phone": f"07{TAG[-7:]}1",
                      "skills": "Masonry, Construction", "location": "Colombo",
                      "district": "Colombo", "experienceYears": 8,
                      "experience": "Eight years of site work.",
                      "certifications": "NVQ Level 3 Masonry",
                      "bio": "Reliable mason.", "available": True}, worker_t)
check("the worker can save skills, district and experience", pr.status_code == 200,
      pr.text[:70])
me = get("/profile", worker_t).json()
check("the extended profile is stored",
      me.get("experienceYears") == 8 and "Masonry" in (me.get("skills") or ""),
      f"years={me.get('experienceYears')} skills={me.get('skills')}")

# ---------------------------------------------------------------------
print("\n4. JOB POSTING")
# ---------------------------------------------------------------------
JOB = f"E2E Mason Job {TAG}"
jr = post("/jobs", {"title": JOB, "category": "Construction", "location": "Colombo",
                    "district": "Colombo", "pay": 2400, "per": "day",
                    "requiredSkills": "Masonry, Construction",
                    "workersNeeded": 1, "expectedUnits": 3,
                    "description": "Three days of masonry work."}, emp_t)
check("the employer can post a job", jr.status_code in (200, 201), jr.text[:80])
job_id = jr.json().get("id") or jr.json().get("Id")
check("the job is retrievable", get(f"/jobs/{job_id}").status_code == 200)

bad = post("/jobs", {"title": "x", "category": "Construction",
                     "location": "Colombo", "pay": 0, "per": "day"}, emp_t)
check("an invalid job is refused", bad.status_code == 400,
      bad.json().get("message", "")[:70] if bad.content else bad.status_code)

check("a worker cannot post a job",
      post("/jobs", {"title": "Nope", "category": "Construction",
                     "location": "Colombo", "pay": 1000, "per": "day"},
           worker_t).status_code in (401, 403))

# ---------------------------------------------------------------------
print("\n5. JOB RECOMMENDATIONS")
# ---------------------------------------------------------------------
rec = get("/recommendations", worker_t)
check("the worker gets recommendations", rec.status_code == 200, rec.status_code)
recs = rec.json()
items = recs if isinstance(recs, list) else recs.get("recommendations", [])
if not isinstance(recs, list):
    check("the profile is complete enough to be matched on",
          recs.get("profileComplete") is True, recs.get("message"))
mine = find(items, "title", JOB)
check("the newly posted job is recommended to a matching worker", len(mine) == 1,
      f"{len(items)} recommendation(s) returned")
if mine:
    r0 = mine[0]
    check("the recommendation carries a match score",
          isinstance(r0.get("matchScore"), (int, float)) and r0["matchScore"] > 0,
          r0.get("matchScore"))
    check("the recommendation explains itself",
          len(r0.get("reasons") or []) > 0, (r0.get("reasons") or [])[:2])

check("an employer cannot ask for worker recommendations",
      get("/recommendations", emp_t).status_code in (401, 403))

# ---------------------------------------------------------------------
print("\n6. SEARCH AND FILTERING")
# ---------------------------------------------------------------------
s1 = get(f"/jobs?search={JOB.replace(' ', '%20')}").json()
rows = s1.get("jobs", s1) if isinstance(s1, dict) else s1
check("keyword search finds the job", len(find(rows, "title", JOB)) == 1, len(rows))

s2 = get("/jobs?minPay=1000000").json()
rows2 = s2.get("jobs", s2) if isinstance(s2, dict) else s2
check("a wage filter excludes cheaper jobs", len(find(rows2, "title", JOB)) == 0)

s3 = get("/jobs?district=Colombo&category=Construction").json()
rows3 = s3.get("jobs", s3) if isinstance(s3, dict) else s3
check("district and category filters work", len(find(rows3, "title", JOB)) == 1)

# ---------------------------------------------------------------------
print("\n7. APPLYING")
# ---------------------------------------------------------------------
ap = post("/applications", {"jobId": job_id, "message": "Eight years of experience."}, worker_t)
check("the worker can apply", ap.status_code in (200, 201), ap.text[:80])

dup = post("/applications", {"jobId": job_id, "message": "again"}, worker_t)
check("applying twice is refused", dup.status_code in (400, 409),
      dup.json().get("message", "")[:70] if dup.content else dup.status_code)

check("an employer cannot apply for a job",
      post("/applications", {"jobId": job_id, "message": "no"}, emp_t).status_code
      in (400, 401, 403))

applicants = get("/employer/applicants", emp_t).json()
rowa = find(applicants, "jobTitle", JOB)
check("the applicant reaches the employer", len(rowa) == 1, len(applicants))
app_id = rowa[0]["id"] if rowa else None
if app_id is None:
    sys.exit("\nCould not find the application; the rest of the lifecycle cannot run.\n")

# ---------------------------------------------------------------------
print("\n8. HIRING")
# ---------------------------------------------------------------------
check("the application starts as pending", rowa[0]["status"] == "pending", rowa[0]["status"])

jump = put(f"/applications/{app_id}/status", {"status": "completed"}, emp_t)
check("pending cannot jump straight to completed", jump.status_code == 400,
      jump.json().get("message", "")[:70] if jump.content else jump.status_code)

sh = put(f"/applications/{app_id}/status", {"status": "shortlisted"}, emp_t)
check("the employer can shortlist", sh.status_code == 200, sh.text[:60])

hi = put(f"/applications/{app_id}/status", {"status": "accepted"}, emp_t)
check("a shortlisted applicant can then be hired", hi.status_code == 200, hi.text[:60])

check("a worker cannot change their own application status",
      put(f"/applications/{app_id}/status", {"status": "completed"}, worker_t).status_code
      in (401, 403))

# ---------------------------------------------------------------------
print("\n9. WORK RECORDS")
# ---------------------------------------------------------------------
w1 = post(f"/applications/{app_id}/work", {"units": 2, "workDate": "2026-01-05"}, emp_t)
check("the employer can record a work day", w1.status_code == 200, w1.text[:70])

dupday = post(f"/applications/{app_id}/work", {"units": 1, "workDate": "2026-01-05"}, emp_t)
check("the same date cannot be recorded twice", dupday.status_code in (400, 409),
      dupday.json().get("message", "")[:60] if dupday.content else dupday.status_code)

sub = post(f"/applications/{app_id}/work", {"units": 1, "workDate": "2026-01-06",
                                            "notes": "Finished the back wall."}, worker_t)
check("the worker can submit their own day", sub.status_code == 200, sub.text[:70])
check("a worker's day is pending, not approved",
      sub.json().get("status") == "pending", sub.json().get("status"))

wk = get(f"/applications/{app_id}/work", emp_t).json()
check("pending work is kept out of the earnings total", wk["totalEarned"] == 4800,
      f"totalEarned={wk['totalEarned']} pending={wk.get('pendingUnits')}")

pending_ids = [r["id"] for r in wk["records"] if r.get("status") == "pending"]
check("the pending day is visible to the employer", len(pending_ids) == 1, pending_ids)

if pending_ids:
    selfapp = put(f"/applications/work/{pending_ids[0]}", {"approve": True}, worker_t)
    check("a worker cannot approve their own day", selfapp.status_code in (401, 403),
          selfapp.status_code)

    appr = put(f"/applications/work/{pending_ids[0]}", {"approve": True}, emp_t)
    check("the employer can approve it", appr.status_code == 200, appr.text[:70])

    wk2 = get(f"/applications/{app_id}/work", emp_t).json()
    check("approved work is added to the total", wk2["totalEarned"] == 7200,
          wk2["totalEarned"])

# ---------------------------------------------------------------------
print("\n10. COMPLETION AND PAYMENT CALCULATION")
# ---------------------------------------------------------------------
cm = put(f"/applications/{app_id}/status", {"status": "completed"}, emp_t)
check("the employer can verify the work as done", cm.status_code == 200, cm.text[:60])

pays = get("/employer/payments", emp_t).json()
pr_row = find(pays, "jobTitle", JOB)
check("a payment is raised automatically", len(pr_row) == 1, len(pays))
pay = pr_row[0] if pr_row else None
if pay is None:
    sys.exit("\nNo payment was raised; the rest of the lifecycle cannot run.\n")

check("the amount is calculated from the work records, not typed in",
      pay["amount"] == 7200, f"expected 7200 (3 days x 2400), got {pay['amount']}")
check("the rate and units are recorded",
      pay["agreedRate"] == 2400 and float(pay["unitsWorked"]) == 3.0,
      f"{pay['agreedRate']} x {pay['unitsWorked']}")

reopen = put(f"/applications/{app_id}/status", {"status": "pending"}, emp_t)
check("a completed job cannot be reopened", reopen.status_code == 400,
      reopen.json().get("message", "")[:60] if reopen.content else reopen.status_code)

extra = post(f"/applications/{app_id}/work", {"units": 1, "workDate": "2026-01-08"}, emp_t)
if extra.status_code == 200:
    pay_after = find(get("/employer/payments", emp_t).json(), "jobTitle", JOB)[0]
    check("work added after completion recalculates the payment",
          pay_after["amount"] == 9600,
          f"expected 9600, got {pay_after['amount']}")
    pay = pay_after
else:
    check("work added after completion is handled, not ignored", False, extra.text[:80])

# ---------------------------------------------------------------------
print("\n11. PAYMENT, PART PAYMENT AND CONFIRMATION")
# ---------------------------------------------------------------------
total = pay["amount"]
part = round(total / 3, 2)

p1 = put(f"/payments/{pay['id']}/pay", {"amount": part, "method": "cash"}, emp_t)
check("the employer can record a part payment", p1.status_code == 200, p1.text[:70])
check("the outstanding balance is reported",
      abs(p1.json()["outstanding"] - (total - part)) < 0.01,
      f"outstanding={p1.json()['outstanding']}")

over = put(f"/payments/{pay['id']}/pay", {"amount": total * 2, "method": "cash"}, emp_t)
check("paying more than is owed is refused", over.status_code == 400,
      over.json().get("message", "")[:60] if over.content else over.status_code)

check("an unrelated worker cannot record a payment",
      put(f"/payments/{pay['id']}/pay", {"amount": 10}, worker_t).status_code in (401, 403))

c1 = put(f"/payments/{pay['id']}/confirm", None, worker_t)
check("the worker can confirm the part payment", c1.status_code == 200, c1.text[:70])
check("the confirmation records an amount, not just a flag",
      abs(c1.json().get("confirmedAmount", 0) - part) < 0.01,
      c1.json().get("confirmedAmount"))
check("a part payment is not reported as fully confirmed",
      c1.json().get("fullyConfirmed") is False, c1.json().get("fullyConfirmed"))

again = put(f"/payments/{pay['id']}/confirm", None, worker_t)
check("confirming twice with no new money is refused", again.status_code == 400,
      again.json().get("message", "")[:70] if again.content else again.status_code)

p2 = put(f"/payments/{pay['id']}/pay", None, emp_t)     # settle the balance
check("the employer can settle the balance", p2.status_code == 200, p2.text[:70])
check("paying the balance resets the worker's confirmation",
      p2.json().get("workerConfirmed") is False, p2.json().get("workerConfirmed"))
check("the newly unconfirmed amount is reported",
      abs(p2.json().get("awaitingConfirmation", 0) - (total - part)) < 0.01,
      p2.json().get("awaitingConfirmation"))

settled = put(f"/payments/{pay['id']}/pay", {"amount": 100}, emp_t)
check("a settled payment cannot be reopened", settled.status_code == 400,
      settled.json().get("message", "")[:60] if settled.content else settled.status_code)

c2 = put(f"/payments/{pay['id']}/confirm", None, worker_t)
check("the worker confirms the balance", c2.status_code == 200, c2.text[:70])
check("the payment is now fully confirmed",
      c2.json().get("fullyConfirmed") is True, c2.json())

mine = find(get("/payments/mine", worker_t).json(), "jobTitle", JOB)
check("the worker sees the settled payment",
      len(mine) == 1 and mine[0]["status"] == "paid",
      mine[0]["status"] if mine else "not found")

aud = get(f"/payments/{pay['id']}/audit", emp_t)
check("the payment has a full audit trail", aud.status_code == 200, aud.status_code)

# ---------------------------------------------------------------------
print("\n12. RATINGS")
# ---------------------------------------------------------------------
r1 = post("/ratings", {"jobId": job_id, "subjectId": worker_id, "stars": 5,
                       "comment": "Good work, finished on time."}, emp_t)
check("the employer can review the worker after completion", r1.status_code == 200,
      r1.text[:70])

r2 = post("/ratings", {"jobId": job_id, "subjectId": worker_id, "stars": 1,
                       "comment": "second attempt"}, emp_t)
check("the same job cannot be reviewed twice", r2.status_code in (400, 409),
      r2.json().get("message", "")[:60] if r2.content else r2.status_code)

r3 = post("/ratings", {"jobId": job_id, "subjectId": emp_id, "stars": 5,
                       "comment": "Paid on time."}, worker_t)
check("the worker can review the employer back", r3.status_code == 200, r3.text[:70])

outsider_t, outsider_id, outsider_email = register("E2E Outsider", "worker")
r4 = post("/ratings", {"jobId": job_id, "subjectId": emp_id, "stars": 1,
                       "comment": "never worked here"}, outsider_t)
check("someone who never worked the job cannot review it", r4.status_code in (400, 403),
      r4.json().get("message", "")[:70] if r4.content else r4.status_code)

r5 = post("/ratings", {"jobId": job_id, "subjectId": outsider_id, "stars": 1,
                       "comment": "never worked for me"}, emp_t)
check("an employer cannot review a worker who never worked for them",
      r5.status_code in (400, 403),
      r5.json().get("message", "")[:70] if r5.content else r5.status_code)

# ---------------------------------------------------------------------
print("\n13. NOTIFICATIONS")
# ---------------------------------------------------------------------
notes = get("/notifications", worker_t).json()
text = " ".join((n.get("title", "") + " " + n.get("message", "")) for n in notes).lower()
check("the worker was notified of being shortlisted", "shortlist" in text)
check("the worker was notified of being hired", "hired" in text)
check("the worker was notified that the work was verified", "verified" in text)
check("the worker was notified about the payment", "payment" in text)
check("the worker was notified about the review", "review" in text)
check("an unread count is available",
      get("/notifications/unread-count", worker_t).status_code == 200)

# ---------------------------------------------------------------------
print("\n14. REPORTS")
# ---------------------------------------------------------------------
wrep = get("/reports/worker", worker_t)
check("the worker report is produced", wrep.status_code == 200, wrep.status_code)
if wrep.ok:
    wr = wrep.json()
    check("the worker report shows real earnings", wr.get("totalEarned", 0) >= total,
          wr.get("totalEarned"))
    check("the worker report counts completed jobs", wr.get("completed", 0) >= 1,
          wr.get("completed"))

erep = get("/reports/employer", emp_t)
check("the employer report is produced", erep.status_code == 200, erep.status_code)
if erep.ok:
    er = erep.json()
    check("the employer report shows real spending", er.get("totalSpent", 0) >= total,
          er.get("totalSpent"))

csv1 = get("/reports/worker/payments.csv", worker_t)
check("the worker CSV export works",
      csv1.status_code == 200 and "," in csv1.text, csv1.text.split("\n")[0][:60])

check("a worker cannot read the admin report",
      get("/reports/admin", worker_t).status_code in (401, 403))

# ---------------------------------------------------------------------
print("\n15. ORGANIZATION VERIFICATION AND PROJECTS")
# ---------------------------------------------------------------------
od = put("/organization", {"organizationName": f"E2E Organization {TAG}",
                           "registrationNumber": f"PV-{TAG}",
                           "address": "42 Galle Road, Colombo 03",
                           "website": "https://example.lk",
                           "district": "Colombo"}, org_t)
check("an organization can save its registration details", od.status_code == 200, od.text[:70])

early = post("/organization/verify", {"notes": "x"}, emp_t)
check("an ordinary employer cannot request organization verification",
      early.status_code in (400, 401, 403), early.status_code)

vr = post("/organization/verify", {"notes": "Registered labour supplier since 2019."}, org_t)
check("an organization can request verification", vr.status_code == 200, vr.text[:70])

twice = post("/organization/verify", {"notes": "again"}, org_t)
check("a second request while one is pending is refused", twice.status_code == 400,
      twice.json().get("message", "")[:60] if twice.content else twice.status_code)

og = get("/organization", org_t).json()
check("the request is recorded as pending",
      og.get("verificationStatus") == "pending", og.get("verificationStatus"))

prj = post("/projects", {"name": f"E2E Project {TAG}", "location": "Kandy",
                         "district": "Kandy", "workersRequired": 4,
                         "budget": 100000, "status": "active"}, org_t)
check("an organization can create a project", prj.status_code == 200, prj.text[:70])
project_id = prj.json().get("id") if prj.ok else None

check("an ordinary employer has no access to projects",
      get("/projects", emp_t).status_code in (401, 403))

if project_id:
    pj = post("/jobs", {"title": f"E2E Project Job {TAG}", "category": "Construction",
                        "location": "Kandy", "district": "Kandy", "pay": 2000,
                        "per": "day", "workersNeeded": 2, "expectedUnits": 5,
                        "projectId": project_id}, org_t)
    check("a job can be posted under the project", pj.status_code in (200, 201), pj.text[:70])

    plist = get("/projects", org_t).json()["projects"]
    this = [p for p in plist if p["id"] == project_id]
    check("the project reports its recruitment position", len(this) == 1)
    if this:
        p0 = this[0]
        check("postings are grouped under the project", p0["jobsPosted"] == 1, p0["jobsPosted"])
        check("positions are counted from the real postings",
              p0["positionsPosted"] == 2, p0["positionsPosted"])
        check("the shortfall is calculated", p0["stillNeeded"] == 4, p0["stillNeeded"])

# ---------------------------------------------------------------------
print("\n16. JOB EDITING")
# ---------------------------------------------------------------------
JOB2 = f"E2E Editable {TAG}"
j2 = post("/jobs", {"title": JOB2, "category": "Construction", "location": "Colombo",
                    "pay": 2000, "per": "day", "workersNeeded": 2,
                    "expectedUnits": 3}, emp_t)
j2id = j2.json().get("id") if j2.ok else None

if j2id:
    ed = put(f"/jobs/{j2id}", {"title": JOB2 + " (edited)", "category": "Cleaning",
                               "location": "Gampaha", "pay": 2200, "per": "day",
                               "workersNeeded": 3, "expectedUnits": 4,
                               "requiredSkills": "Cleaning"}, emp_t)
    check("the employer can edit their own job", ed.status_code == 200, ed.text[:70])

    body = get(f"/jobs/{j2id}").json()
    jd = body.get("job", body)
    check("the edit is saved", jd["title"] == JOB2 + " (edited)" and jd["pay"] == 2200,
          f"{jd['title']} / {jd['pay']}")
    check("a worker cannot edit someone else's job",
          put(f"/jobs/{j2id}", {"title": "hijack", "category": "Cleaning",
                                "location": "Gampaha", "pay": 1, "per": "day",
                                "workersNeeded": 1}, worker_t).status_code in (401, 403))

# ---------------------------------------------------------------------
print("\n17. ADMIN FUNCTIONS")
# ---------------------------------------------------------------------
ad = post("/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if not ad.ok:
    skip("administrator sign-in", f"{ADMIN_EMAIL} did not accept the password "
                                  "(set DW_ADMIN_PASSWORD) — admin checks not run")
    admin_t = None
else:
    admin_t = ad.json()["token"]
    check("the administrator can sign in", True)

if admin_t:
    check("the admin can list users", get("/admin/users", admin_t).status_code == 200)
    check("a worker cannot list users", get("/admin/users", worker_t).status_code in (401, 403))

    q = get("/admin/verifications", admin_t)
    check("the verification queue is readable", q.status_code == 200, q.status_code)
    queue = q.json() if q.ok else []
    qrows = queue if isinstance(queue, list) else queue.get("requests", [])
    waiting = [x for x in qrows if x.get("userId") == org_id]
    check("the organization's request is in the queue", len(waiting) == 1,
          f"{len(qrows)} request(s) waiting")

    bad_v = put(f"/admin/verifications/{org_id}", {"approve": False, "note": ""}, admin_t)
    check("rejecting without a reason is refused", bad_v.status_code == 400,
          bad_v.json().get("message", "")[:60] if bad_v.content else bad_v.status_code)

    ap_v = put(f"/admin/verifications/{org_id}",
               {"approve": True, "note": "Registration checked."}, admin_t)
    check("the admin can approve verification", ap_v.status_code == 200, ap_v.text[:70])

    og2 = get("/organization", org_t).json()
    check("the organization is now verified",
          og2.get("verificationStatus") == "verified", og2.get("verificationStatus"))

    cname = f"E2E Sector {TAG}"
    cr = post("/categories", {"name": cname, "description": "Created by the end-to-end test."},
              admin_t)
    check("the admin can add a job category", cr.status_code in (200, 201), cr.text[:70])
    check("a worker cannot add a category",
          post("/categories", {"name": "nope"}, worker_t).status_code in (401, 403))

    msg = post("/contact", {"name": "E2E Tester", "email": "e2e@dwtest.lk",
                            "subject": f"E2E contact {TAG}",
                            "message": "Submitted by the end-to-end test."})
    check("the public contact form accepts a message", msg.status_code == 200, msg.text[:70])

    inbox = get("/admin/messages", admin_t)
    rows_i = inbox.json() if inbox.ok else []
    rows_i = rows_i if isinstance(rows_i, list) else rows_i.get("messages", [])
    check("the message reaches the admin inbox",
          any(f"E2E contact {TAG}" == m.get("subject") for m in rows_i),
          f"{len(rows_i)} message(s) in the inbox")

    arep = get("/reports/admin", admin_t)
    check("the admin report is produced", arep.status_code == 200, arep.status_code)

    # Deactivation must preserve financial history.
    dl = delete(f"/admin/users/{outsider_id}", admin_t)
    check("deleting a user deactivates them instead of destroying records",
          dl.status_code == 200, dl.text[:70])
    relog = post("/auth/login", {"email": outsider_email, "password": PW})
    check("the deactivated account can no longer sign in",
          relog.status_code in (400, 401, 403), relog.status_code)
    still = find(get("/employer/payments", emp_t).json(), "jobTitle", JOB)
    check("payment history survives a deactivation", len(still) == 1)

# ---------------------------------------------------------------------
print("\n" + "=" * 74)
print(f"RESULT: {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
print("=" * 74)
print(f"Target : {BASE}")
print(f"Run tag: {TAG}")
print("This run created accounts, jobs and a project tagged with the run tag above.")
print("Nothing was deleted. You can run this script again at any time.")

if failed:
    print("\nFAILURES:")
    for f in failed:
        print("  -", f)
    sys.exit(1)

print("\nThe complete process ran against the real backend:")
print("  registration -> job posting -> recommendation -> application -> hiring")
print("  -> work records -> completion -> payment -> worker confirmation -> ratings")
print("  plus admin functions, organization approval, projects, notifications and reports.")
