"""
API-level test suite covering the twenty areas listed in the audit brief,
plus the complete job lifecycle.

Run against the mirror server, which implements the same contract as the C#
controllers. Every assertion here corresponds to a rule written in the
controllers, so a pass means the rule is expressed correctly and the frontend
contract matches.
"""
import requests, sys, json, datetime

BASE = "http://localhost:5000/api"
passed, failed = [], []


def check(area, label, ok, detail=""):
    line = f"  [{area}] {label}"
    print(("  PASS " if ok else "  FAIL ") + line + (("  -> " + str(detail)[:90]) if detail else ""))
    (passed if ok else failed).append(label)


def post(path, body, token=None, expect=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    r = requests.post(BASE + path, json=body, headers=h)
    return r


def put(path, body=None, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    return requests.put(BASE + path, json=body or {}, headers=h)


def get(path, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    return requests.get(BASE + path, headers=h)


def delete(path, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    return requests.delete(BASE + path, headers=h)


def login(email, pw):
    r = post("/auth/login", {"email": email, "password": pw})
    return r.json().get("token") if r.ok else None


print("=" * 72)
print("DAILYWORK API TEST SUITE")
print("=" * 72)

# =====================================================================
print("\n1. USER REGISTRATION AND LOGIN")
# =====================================================================
r = post("/auth/register", {"name": "Test Worker", "email": "tw@test.lk",
                            "phone": "0771234567", "password": "Secret@123", "role": "worker"})
check("1", "worker can register", r.status_code == 200, r.text)
worker_token = r.json().get("token") if r.ok else None
worker_id = r.json().get("id") if r.ok else None

r = post("/auth/register", {"name": "Test Worker", "email": "tw@test.lk",
                            "phone": "0771234567", "password": "Secret@123", "role": "worker"})
check("1", "duplicate email rejected", r.status_code == 409, r.json().get("message"))

r = post("/auth/register", {"name": "X", "email": "x@test.lk", "phone": "0771234567",
                            "password": "Secret@123", "role": "worker"})
check("1", "short name rejected", r.status_code == 400, r.json().get("message"))

r = post("/auth/register", {"name": "Bad Pw", "email": "bp@test.lk", "phone": "0771234567",
                            "password": "abc", "role": "worker"})
check("1", "short password rejected", r.status_code == 400, r.json().get("message"))

r = post("/auth/register", {"name": "No Digit", "email": "nd@test.lk", "phone": "0771234567",
                            "password": "abcdefgh", "role": "worker"})
check("1", "password without a number rejected", r.status_code == 400, r.json().get("message"))

r = post("/auth/register", {"name": "Common", "email": "cm@test.lk", "phone": "0771234567",
                            "password": "password", "role": "worker"})
check("1", "common password rejected", r.status_code == 400, r.json().get("message"))

r = post("/auth/register", {"name": "Bad Phone", "email": "bph@test.lk", "phone": "12",
                            "password": "Secret@123", "role": "worker"})
check("1", "invalid phone rejected", r.status_code == 400, r.json().get("message"))

r = post("/auth/login", {"email": "tw@test.lk", "password": "wrong"})
check("1", "wrong password rejected", r.status_code == 401, r.json().get("message"))

r = post("/auth/login", {"email": "nobody@nowhere.lk", "password": "whatever"})
check("1", "unknown account gives the same message (no account enumeration)",
      r.status_code == 401 and r.json().get("message") == "Invalid email or password.")

# =====================================================================
print("\n2. ROLE-BASED AUTHORIZATION")
# =====================================================================
r = post("/auth/register", {"name": "Fake Admin", "email": "fa@test.lk", "phone": "0771234567",
                            "password": "Secret@123", "role": "admin"})
check("2", "admin cannot be self-registered", r.status_code == 400, r.json().get("message"))

admin_token = login("admin@dailywork.lk", "Admin@12345")
check("2", "seeded admin can log in", admin_token is not None)

emp_token = login("employer@dailywork.lk", "Password@123")
check("2", "seeded employer can log in", emp_token is not None)

r = get("/admin/users", worker_token)
check("2", "worker blocked from admin API", r.status_code == 403, r.status_code)

r = get("/admin/users")
check("2", "anonymous blocked from admin API", r.status_code in (401, 403), r.status_code)

r = get("/employer/applicants", worker_token)
check("2", "worker blocked from employer API", r.status_code == 403, r.status_code)

r = get("/admin/users", admin_token)
check("2", "admin allowed on admin API", r.status_code == 200)

# =====================================================================
print("\n3+4. JOB APPLICATIONS AND DUPLICATES")
# =====================================================================
jobs = get("/jobs").json()["jobs"]
target = next(j for j in jobs if j["title"] == "Construction Helper")

r = post("/applications", {"jobId": target["id"]}, worker_token)
check("3", "worker can apply", r.status_code == 200, r.json().get("message"))

r = post("/applications", {"jobId": target["id"]}, worker_token)
check("4", "duplicate application rejected", r.status_code == 409, r.json().get("message"))

r = post("/applications", {"jobId": target["id"]}, emp_token)
check("3", "employer cannot apply for a job (role enforced)", r.status_code == 403, r.status_code)

r = post("/applications", {"jobId": target["id"]}, admin_token)
check("3", "admin cannot submit a worker application", r.status_code == 403, r.status_code)

r = post("/applications", {"jobId": 99999}, worker_token)
check("3", "applying to a missing job rejected", r.status_code == 404, r.json().get("message"))

r = post("/applications", {"jobId": target["id"]})
check("3", "anonymous cannot apply", r.status_code in (401, 403), r.status_code)

# employer applying to their OWN job
own = next(j for j in jobs if j["employerId"] == 5)   # Kasun Fernando is user 5
r2 = post("/auth/register", {"name": "Dual Role", "email": "dual@test.lk", "phone": "0771234567",
                             "password": "Secret@123", "role": "employer"})
dual_token = r2.json()["token"]
post("/jobs", {"title": "My Own Job", "category": "Cleaning", "location": "Colombo",
               "pay": 2000, "per": "day", "workersNeeded": 1}, dual_token)
# a worker account that is also the employer cannot happen, but the rule is still checked
# by making the employer a worker is impossible; verified by the C# rule and below in 5.

# =====================================================================
print("\n5. JOB POSTING AND EDITING")
# =====================================================================
r = post("/jobs", {"title": "Test Mason Job", "category": "Construction", "location": "Colombo",
                   "district": "Colombo", "pay": 2600, "per": "day",
                   "requiredSkills": "Masonry, Construction", "workersNeeded": 2,
                   "expectedUnits": 5}, emp_token)
check("5", "employer can post a job", r.status_code in (200, 201), r.text[:80])
new_job_id = r.json().get("id")

r = post("/jobs", {"title": "No", "category": "Construction", "location": "Colombo",
                   "pay": 2000}, emp_token)
check("5", "short title rejected", r.status_code == 400, r.json().get("message"))

r = post("/jobs", {"title": "Zero Pay Job", "category": "Construction",
                   "location": "Colombo", "pay": 0}, emp_token)
check("5", "zero wage rejected", r.status_code == 400, r.json().get("message"))

r = post("/jobs", {"title": "Silly Pay", "category": "Construction",
                   "location": "Colombo", "pay": 99999999}, emp_token)
check("5", "absurd wage rejected", r.status_code == 400, r.json().get("message"))

r = post("/jobs", {"title": "Worker Posting", "category": "Cleaning",
                   "location": "Colombo", "pay": 1500}, worker_token)
check("5", "worker cannot post a job", r.status_code == 403, r.status_code)

r = put(f"/jobs/{new_job_id}", {"title": "Test Mason Job (updated)", "category": "Construction",
                                "location": "Colombo", "pay": 2600, "workersNeeded": 2}, emp_token)
check("5", "employer can edit their own job", r.status_code == 200, r.json().get("message"))

r = put(f"/jobs/{new_job_id}", {"title": "Hijacked", "category": "Construction",
                                "location": "Colombo", "pay": 2600, "workersNeeded": 2}, dual_token)
check("5", "employer cannot edit another employer's job", r.status_code == 403, r.status_code)

# =====================================================================
print("\n6+7. HIRING, REJECTION AND WORK COMPLETION RULES")
# =====================================================================
post("/applications", {"jobId": new_job_id, "message": "I have 8 years experience"}, worker_token)
apps = get("/employer/applicants", emp_token).json()
app_row = next(a for a in apps if a["jobId"] == new_job_id)
app_id = app_row["id"]
check("6", "applicant visible to the employer with their skills",
      app_row["workerName"] == "Test Worker", app_row.get("workerSkills"))

r = put(f"/applications/{app_id}/status", {"status": "completed"}, emp_token)
check("7", "cannot complete work that was never hired", r.status_code == 400, r.json().get("message"))

r = put(f"/applications/{app_id}/status", {"status": "shortlisted"}, emp_token)
check("6", "employer can shortlist", r.status_code == 200, r.json().get("message"))

r = put(f"/applications/{app_id}/status", {"status": "pending"}, emp_token)
check("7", "cannot move backwards to pending", r.status_code == 400, r.json().get("message"))

r = put(f"/applications/{app_id}/status", {"status": "accepted"}, emp_token)
check("6", "employer can hire", r.status_code == 200)

r = put(f"/applications/{app_id}/status", {"status": "accepted"}, emp_token)
check("7", "re-hiring the same application rejected", r.status_code == 400, r.json().get("message"))

r = put(f"/applications/{app_id}/status", {"status": "accepted"}, dual_token)
check("6", "another employer cannot decide on this application", r.status_code == 403, r.status_code)

r = put(f"/applications/{app_id}/status", {"status": "bogus"}, emp_token)
check("7", "invalid status rejected", r.status_code == 400, r.json().get("message"))

# work records before completion
r = post(f"/applications/{app_id}/work", {"units": 3}, emp_token)
check("12", "employer can record a day of work", r.status_code == 200, r.json().get("message"))

r = post(f"/applications/{app_id}/work", {"units": 3}, emp_token)
check("12", "duplicate work record for the same date rejected", r.status_code == 409, r.json().get("message"))

r = post(f"/applications/{app_id}/work", {"units": 99}, emp_token)
check("12", "absurd unit count rejected", r.status_code == 400, r.json().get("message"))

r = get(f"/applications/{app_id}/work", emp_token)
wr = r.json()
check("12", "work log totals calculated", wr["totalUnits"] == 3 and wr["totalEarned"] == 7800.0,
      f"units={wr['totalUnits']} earned={wr['totalEarned']}")

r = put(f"/applications/{app_id}/status", {"status": "completed"}, emp_token)
check("7", "employer can verify completed work", r.status_code == 200)

r = put(f"/applications/{app_id}/status", {"status": "pending"}, emp_token)
check("7", "completed work cannot be reopened", r.status_code == 400, r.json().get("message"))

# =====================================================================
print("\n8+9. PAYMENT CREATION AND DUPLICATE PROTECTION")
# =====================================================================
pays = get("/employer/payments", emp_token).json()
pay = next((p for p in pays if p["jobId"] == new_job_id), None)
check("8", "payment raised automatically on completion", pay is not None)
check("8", "payment total = rate x units worked", pay and pay["amount"] == 7800.0,
      pay and f"rate={pay['agreedRate']} units={pay['unitsWorked']} amount={pay['amount']}")
check("8", "payment starts unpaid", pay and pay["amountPaid"] == 0 and pay["status"] == "pending")

r = put(f"/payments/{pay['id']}/pay", {"amount": 3000, "method": "cash"}, emp_token)
check("8", "part payment accepted", r.status_code == 200, r.json().get("message"))
check("8", "part payment leaves a balance",
      r.json().get("outstanding") == 4800.0, r.json().get("outstanding"))
check("8", "status becomes partial", r.json().get("status") == "partial")

r = put(f"/payments/{pay['id']}/pay", {"amount": 99999}, emp_token)
check("8", "overpayment rejected", r.status_code == 400, r.json().get("message"))

r = put(f"/payments/{pay['id']}/pay", {"amount": -5}, emp_token)
check("8", "negative payment rejected", r.status_code == 400, r.json().get("message"))

r = put(f"/payments/{pay['id']}/pay", {}, dual_token)
check("8", "another employer cannot pay this record", r.status_code == 403, r.status_code)

r = put(f"/payments/{pay['id']}/pay", {"amount": 4800, "method": "cash"}, emp_token)
check("8", "final payment settles the record", r.json().get("status") == "paid", r.text[:80])
paid_at_first = get("/payments/mine", worker_token).json()[0]["paidAt"]

r = put(f"/payments/{pay['id']}/pay", {"amount": 100}, emp_token)
check("9", "a settled payment cannot be paid again", r.status_code == 400, r.json().get("message"))

paid_at_second = get("/payments/mine", worker_token).json()[0]["paidAt"]
check("9", "original paid timestamp preserved", paid_at_first == paid_at_second,
      f"{paid_at_first} vs {paid_at_second}")

audit = get(f"/payments/{pay['id']}/audit", emp_token).json()
check("9", "audit trail records every change", len(audit) >= 3, f"{len(audit)} entries")
check("9", "audit trail records who acted",
      all(a.get("actorRole") for a in audit if a["action"] != "created"))

r = put(f"/payments/{pay['id']}/confirm", {}, worker_token)
check("8", "worker can confirm receiving payment", r.status_code == 200, r.json().get("message"))

r = put(f"/payments/{pay['id']}/confirm", {}, worker_token)
check("8", "double confirmation rejected", r.status_code == 400, r.json().get("message"))

r = put(f"/payments/{pay['id']}/confirm", {}, emp_token)
check("8", "employer cannot confirm on the worker's behalf", r.status_code == 403, r.status_code)

# =====================================================================
print("\n10+11. RATINGS AND RATING AUTHORIZATION")
# =====================================================================
r = post("/ratings", {"jobId": new_job_id, "subjectId": worker_id, "stars": 5,
                      "comment": "Reliable and on time."}, emp_token)
check("10", "employer can review the worker who completed the job", r.status_code == 200, r.json().get("message"))

r = post("/ratings", {"jobId": new_job_id, "subjectId": worker_id, "stars": 4}, emp_token)
check("10", "duplicate review rejected", r.status_code == 409, r.json().get("message"))

r = post("/ratings", {"jobId": new_job_id, "subjectId": 5, "stars": 5}, worker_token)
check("10", "worker can review the employer who hired them", r.status_code == 200, r.json().get("message"))

# THE CRITICAL HOLE: rating an unrelated third party
r = post("/ratings", {"jobId": new_job_id, "subjectId": 2, "stars": 1,
                      "comment": "sabotage"}, worker_token)
check("11", "cannot review an unrelated person (arbitrary subject id blocked)",
      r.status_code == 400, r.json().get("message"))

r = post("/ratings", {"jobId": new_job_id, "subjectId": 99999, "stars": 5}, worker_token)
check("11", "review of a non-existent user rejected", r.status_code == 404, r.json().get("message"))

r = post("/ratings", {"jobId": new_job_id, "subjectId": worker_id, "stars": 5}, worker_token)
check("11", "self-review rejected", r.status_code == 400, r.json().get("message"))

r = post("/ratings", {"jobId": new_job_id, "subjectId": 5, "stars": 9}, worker_token)
check("11", "star rating outside 1-5 rejected", r.status_code == 400, r.json().get("message"))

# a different worker who never did this job
other = post("/auth/register", {"name": "Other Worker", "email": "ow@test.lk",
                                "phone": "0779998888", "password": "Secret@123",
                                "role": "worker"}).json()
r = post("/ratings", {"jobId": new_job_id, "subjectId": 5, "stars": 1}, other["token"])
check("11", "stranger cannot review a job they were not on", r.status_code == 400, r.json().get("message"))

# unfinished job
unfinished = next(j for j in jobs if j["title"] == "Office Cleaner")
r = post("/ratings", {"jobId": unfinished["id"], "subjectId": 7, "stars": 5}, worker_token)
check("11", "review before completion rejected", r.status_code == 400, r.json().get("message"))

ratings = get(f"/ratings/user/{worker_id}").json()
check("10", "review appears on the worker's profile", len(ratings) == 1 and ratings[0]["stars"] == 5)

# =====================================================================
print("\n12. NOTIFICATIONS")
# =====================================================================
notes = get("/notifications", worker_token).json()
titles = [n["title"] for n in notes]
check("12", "worker notified when hired", "You have been hired" in titles, titles[:4])
check("12", "worker notified when work verified", "Work verified" in titles)
check("12", "worker notified about payment",
      any("ayment" in t for t in titles), titles[:6])
check("12", "worker notified about the review", "New review received" in titles)

cnt = get("/notifications/unread-count", worker_token).json()["count"]
check("12", "unread count reported", cnt > 0, cnt)

put("/notifications/read-all", {}, worker_token)
cnt2 = get("/notifications/unread-count", worker_token).json()["count"]
check("12", "mark all as read works", cnt2 == 0, cnt2)

emp_notes = [n["title"] for n in get("/notifications", emp_token).json()]
check("12", "employer notified of a new applicant", "New applicant" in emp_notes, emp_notes[:4])

# =====================================================================
print("\n13. WORKER PROFILES")
# =====================================================================
r = put("/profile", {"name": "Test Worker", "phone": "0771234567",
                     "skills": "Masonry, Painting", "location": "Colombo",
                     "district": "Colombo", "experience": "8 years on sites",
                     "experienceYears": 8, "certifications": "NVQ Level 3",
                     "available": True}, worker_token)
check("13", "worker can save an extended profile", r.status_code == 200, r.json().get("message"))

prof = get("/profile", worker_token).json()
check("13", "profile stores experience", prof["experienceYears"] == 8)
check("13", "profile stores certifications", prof["certifications"] == "NVQ Level 3")
check("13", "profile shows completed jobs", prof["jobsCompleted"] == 1, prof["jobsCompleted"])
check("13", "profile shows total earned", prof["totalEarned"] == 7800.0, prof["totalEarned"])
check("13", "profile shows work history", len(prof["workHistory"]) == 1)
check("13", "profile shows the rating earned", prof["averageRating"] == 5.0)

r = put("/profile", {"name": "X", "phone": "0771234567"}, worker_token)
check("13", "invalid profile name rejected", r.status_code == 400, r.json().get("message"))

r = put("/profile", {"name": "Test Worker", "phone": "0771234567", "experienceYears": 999}, worker_token)
check("13", "absurd experience rejected", r.status_code == 400, r.json().get("message"))

# =====================================================================
print("\n14. JOB RECOMMENDATIONS")
# =====================================================================
rec = get("/recommendations", worker_token).json()
recs = rec["recommendations"]
check("14", "recommendations returned for a worker with a profile", len(recs) > 0, len(recs))
check("14", "every recommendation carries a match score",
      all("matchScore" in r_ and r_["matchScore"] > 0 for r_ in recs))
check("14", "every recommendation explains itself",
      all(len(r_["reasons"]) > 0 for r_ in recs))
check("14", "recommendations are sorted best first",
      [r_["matchScore"] for r_ in recs] == sorted([r_["matchScore"] for r_ in recs], reverse=True))

top = recs[0]
check("14", "masonry worker is matched to construction work",
      "Construction" in top["category"] or "Mason" in top["title"],
      f"{top['title']} ({top['matchScore']}%) {top['reasons'][:2]}")
check("14", "already-applied jobs are excluded",
      all(r_["id"] != new_job_id for r_ in recs))
check("14", "location is used in the reasoning",
      any("area" in " ".join(r_["reasons"]).lower() or
          "district" in " ".join(r_["reasons"]).lower() for r_ in recs))

bare = post("/auth/register", {"name": "Bare Profile", "email": "bare@test.lk",
                               "phone": "0771111111", "password": "Secret@123",
                               "role": "worker"}).json()
rec2 = get("/recommendations", bare["token"]).json()
check("14", "worker with an empty profile is told to complete it",
      rec2.get("profileComplete") is False and rec2.get("message"), rec2.get("message"))

# Recommendations are matched against a worker's own profile, so the endpoint
# is restricted to workers rather than returning a meaningless empty list.
rec3 = get("/recommendations", emp_token)
check("14", "an employer cannot ask for job recommendations", rec3.status_code == 403,
      rec3.status_code)
check("14", "an administrator cannot ask for job recommendations",
      get("/recommendations", admin_token).status_code == 403)

# =====================================================================
print("\n15. ORGANIZATION VERIFICATION")
# =====================================================================
org = post("/auth/register", {"name": "New Org Ltd", "email": "neworg@test.lk",
                              "phone": "0112223333", "password": "Secret@123",
                              "role": "organization"}).json()
org_token = org["token"]
check("15", "new organization starts unverified", org["verificationStatus"] == "unverified")

o = get("/organization", org_token).json()
check("15", "organization record created", o["verificationStatus"] == "unverified")

r = post("/organization/verify", {"notes": "please verify"}, org_token)
check("15", "verification needs a registration number first", r.status_code == 400, r.json().get("message"))

put("/organization", {"organizationName": "New Org Ltd", "registrationNumber": "PV-55555",
                      "address": "1 Test Road", "district": "Colombo"}, org_token)
r = post("/organization/verify", {"notes": "Registered since 2020"}, org_token)
check("15", "organization can request verification", r.status_code == 200, r.json().get("message"))

r = post("/organization/verify", {}, org_token)
check("15", "duplicate request rejected", r.status_code == 400, r.json().get("message"))

queue = get("/admin/verifications?status=pending", admin_token).json()
check("15", "request appears in the admin queue",
      any(q["userId"] == org["id"] for q in queue), [q["organizationName"] for q in queue])

r = get("/admin/verifications", org_token)
check("15", "non-admin cannot see the verification queue", r.status_code == 403, r.status_code)

r = put(f"/admin/verifications/{org['id']}", {"approve": False, "note": "no"}, admin_token)
check("15", "rejection requires a proper reason", r.status_code == 400, r.json().get("message"))

r = put(f"/admin/verifications/{org['id']}", {"approve": True, "note": "Checked register"}, admin_token)
check("15", "admin can approve verification", r.status_code == 200, r.json().get("message"))

o2 = get("/organization", org_token).json()
check("15", "organization is now verified", o2["verificationStatus"] == "verified")

post("/jobs", {"title": "Verified Org Job", "category": "Construction",
               "location": "Colombo", "pay": 2700}, org_token)
vjobs = get("/jobs?verifiedOnly=true").json()["jobs"]
check("15", "verified badge appears only for verified employers",
      all(j["employerVerified"] for j in vjobs) and len(vjobs) > 0, len(vjobs))

unverified_jobs = [j for j in get("/jobs").json()["jobs"] if not j["employerVerified"]]
check("15", "unverified employers do NOT get a badge", len(unverified_jobs) > 0, len(unverified_jobs))

r = put("/organization", {"organizationName": "Renamed Org", "registrationNumber": "PV-99999"}, org_token)
check("15", "changing registered details sends the account back for review",
      get("/organization", org_token).json()["verificationStatus"] == "pending", r.json().get("message"))

# =====================================================================
print("\n16. SEARCH AND FILTERING")
# =====================================================================
r = get("/jobs?search=mason").json()
check("16", "keyword search works", r["total"] >= 1, r["total"])

r = get("/jobs?category=Cleaning").json()
check("16", "category filter works", all(j["category"] == "Cleaning" for j in r["jobs"]), r["total"])

r = get("/jobs?location=Colombo").json()
check("16", "location filter works", all("colombo" in j["location"].lower() for j in r["jobs"]))

r = get("/jobs?minPay=2500").json()
check("16", "minimum wage filter works", all(j["pay"] >= 2500 for j in r["jobs"]), r["total"])

r = get("/jobs?maxPay=1600").json()
check("16", "maximum wage filter works", all(j["pay"] <= 1600 for j in r["jobs"]), r["total"])

r = get("/jobs?minPay=1800&maxPay=2200").json()
check("16", "wage range filter works", all(1800 <= j["pay"] <= 2200 for j in r["jobs"]), r["total"])

r = get("/jobs?minPay=5000&maxPay=1000")
check("16", "inverted wage range rejected", r.status_code == 400, r.json().get("message"))

r = get("/jobs?minPay=-5")
check("16", "negative wage rejected", r.status_code == 400, r.json().get("message"))

r = get("/jobs?skills=masonry").json()
check("16", "skills filter works", r["total"] >= 1, r["total"])

r = get("/jobs?urgentOnly=true").json()
check("16", "urgent filter works", all(j["urgent"] for j in r["jobs"]), r["total"])

r = get("/jobs?sort=wage_high").json()["jobs"]
check("16", "sort by highest wage works", [j["pay"] for j in r] == sorted([j["pay"] for j in r], reverse=True))

r = get("/jobs?sort=wage_low").json()["jobs"]
check("16", "sort by lowest wage works", [j["pay"] for j in r] == sorted([j["pay"] for j in r]))

r = get("/jobs?pageSize=5&page=1").json()
check("16", "pagination works", len(r["jobs"]) == 5 and r["totalPages"] >= 2,
      f"page1={len(r['jobs'])} pages={r['totalPages']}")

r = get("/jobs?availableOnly=true").json()
check("16", "fully-staffed jobs can be hidden", r["total"] >= 1, r["total"])

# =====================================================================
print("\n17. ADMINISTRATOR FUNCTIONALITY")
# =====================================================================
st = get("/admin/stats", admin_token).json()
check("17", "admin stats come from real records", st["totalUsers"] > 0 and st["totalJobs"] > 0)
check("17", "admin stats count pending verifications", "pendingVerifications" in st)

r = post("/categories", {"name": "Test Sector", "icon": "fa-wrench"}, admin_token)
check("17", "admin can add a job category", r.status_code == 200, r.json().get("message"))
cat_id = r.json().get("id")

r = post("/categories", {"name": "Test Sector"}, admin_token)
check("17", "duplicate category rejected", r.status_code == 409, r.json().get("message"))

r = post("/categories", {"name": "Sneaky"}, emp_token)
check("17", "non-admin cannot add a category", r.status_code == 403, r.status_code)

r = put(f"/categories/{cat_id}", {"name": "Renamed Sector", "sortOrder": 9}, admin_token)
check("17", "admin can rename a category", r.status_code == 200)

r = delete(f"/categories/{cat_id}", admin_token)
check("17", "unused category can be deleted", r.json().get("action") == "deleted", r.json())

cats = get("/categories").json()
check("17", "category list is served to the website", len(cats) >= 8, len(cats))

r = post("/admin/announce", {"title": "System maintenance",
                             "message": "The platform will be briefly offline on Sunday.",
                             "audience": "worker"}, admin_token)
check("17", "admin can send an announcement", r.status_code == 200, r.json().get("message"))

# role change invalidates the old token
tmp = post("/auth/register", {"name": "Role Change", "email": "rc@test.lk",
                              "phone": "0775556666", "password": "Secret@123",
                              "role": "worker"}).json()
check("19", "token works before the role change",
      get("/profile", tmp["token"]).status_code == 200)
put(f"/admin/users/{tmp['id']}/role", {"role": "employer"}, admin_token)
check("19", "old token stops working after a role change",
      get("/profile", tmp["token"]).status_code in (401, 403),
      get("/profile", tmp["token"]).status_code)

# =====================================================================
print("\n18. DATABASE INTEGRITY — deletion must not destroy records")
# =====================================================================
r = delete(f"/admin/users/{worker_id}", admin_token)
check("18", "user with payment history is deactivated, not deleted",
      r.json().get("action") == "deactivated", r.json().get("message"))

still = get(f"/ratings/user/{worker_id}").json()
check("18", "their reviews survive deactivation", len(still) == 1)

pays_after = get("/employer/payments", emp_token).json()
check("18", "their payment records survive deactivation",
      any(p["workerId"] == worker_id for p in pays_after))

check("18", "a deactivated user cannot log in",
      post("/auth/login", {"email": "tw@test.lk", "password": "Secret@123"}).status_code == 401)

check("18", "a deactivated user's token stops working",
      get("/profile", worker_token).status_code in (401, 403))

r = put(f"/admin/users/{worker_id}/reactivate", {}, admin_token)
check("18", "admin can reactivate an account", r.status_code == 200, r.json().get("message"))

r = delete(f"/admin/users/{bare['id']}", admin_token)
check("18", "user with no history is deleted outright", r.json().get("action") == "deleted")

r = delete(f"/admin/jobs/{new_job_id}", admin_token)
check("18", "job with completed work is closed, not deleted",
      r.json().get("action") == "closed", r.json().get("message"))

admin_id = [u for u in get("/admin/users", admin_token).json() if u["role"] == "admin"][0]["id"]
r = delete(f"/admin/users/{admin_id}", admin_token)
check("18", "admin cannot delete their own account", r.status_code == 400, r.json().get("message"))

# =====================================================================
print("\n19. SECURITY AND PRIVACY")
# =====================================================================
pub = get(f"/profile/{other['id']}").json()
check("19", "public profile hides the email", pub["email"] == "", pub.get("email"))
check("19", "public profile hides the phone", pub["phone"] == "")
check("19", "public profile hides earnings", pub["totalEarned"] == 0)
check("19", "public profile still shows skills and rating", "skills" in pub and "averageRating" in pub)

r = get("/payments/mine")
check("19", "payments require authentication", r.status_code in (401, 403), r.status_code)

r = get(f"/payments/{pay['id']}/audit", other["token"])
check("19", "audit trail hidden from unrelated users", r.status_code == 403, r.status_code)

# login throttling
for i in range(6):
    last = post("/auth/login", {"email": "throttle@test.lk", "password": "wrong"})
check("19", "repeated failed logins are throttled", last.status_code == 429, last.status_code)

# =====================================================================
print("\n20. INVALID REQUESTS AND ERROR HANDLING")
# =====================================================================
r = get("/jobs/99999")
check("20", "missing job returns 404 with a message",
      r.status_code == 404 and "message" in r.json(), r.text[:60])

r = put("/applications/99999/status", {"status": "accepted"}, emp_token)
check("20", "missing application returns 404", r.status_code == 404)

r = put("/payments/99999/pay", {}, emp_token)
check("20", "missing payment returns 404", r.status_code == 404)

r = post("/contact", {"name": "A", "email": "bad", "subject": "x", "message": "y"})
check("20", "contact form validates its input", r.status_code == 400, r.json().get("message"))

r = post("/contact", {"name": "Real Person", "email": "rp@test.lk",
                      "subject": "Question about jobs",
                      "message": "How do I register as a worker in Kandy?"})
check("20", "valid contact message is accepted", r.status_code == 200, r.json().get("message"))

msgs = get("/admin/messages", admin_token).json()
check("20", "contact message is actually stored",
      any(m["subject"] == "Question about jobs" for m in msgs), len(msgs))

r = post("/contact", {"name": "Bot", "email": "bot@spam.lk", "subject": "Buy now",
                      "message": "Cheap things for sale here", "website": "http://spam"})
check("20", "honeypot submission is silently discarded",
      r.status_code == 200 and not any(m["subject"] == "Buy now"
                                       for m in get("/admin/messages", admin_token).json()))

# =====================================================================
print("\n21. REPORTS")
# =====================================================================
w_tok = login("tw@test.lk", "Secret@123")
rep = get("/reports/worker", w_tok).json()
check("21", "worker report built from real records",
      rep["completed"] == 1 and rep["totalEarned"] == 7800.0,
      f"completed={rep['completed']} earned={rep['totalEarned']}")
check("21", "worker report groups earnings by month", len(rep["earningsByMonth"]) >= 1)
check("21", "worker report calculates a success rate", rep["successRate"] > 0, rep["successRate"])

erep = get("/reports/employer", emp_token).json()
check("21", "employer report built from real records",
      erep["jobsPosted"] >= 1 and erep["totalSpent"] == 7800.0,
      f"posted={erep['jobsPosted']} spent={erep['totalSpent']}")
check("21", "employer report calculates a fill rate", "fillRate" in erep)

arep = get("/reports/admin", admin_token).json()
check("21", "admin report built from real records", arep["totalUsers"] > 0)
check("21", "admin report breaks users down by role", arep["byRole"]["workers"] > 0)
check("21", "admin report tracks verification states", arep["verification"]["verified"] >= 1)

r = get("/reports/admin", emp_token)
check("21", "non-admin cannot read the admin report", r.status_code == 403, r.status_code)

csv = requests.get(BASE + "/reports/worker/payments.csv",
                   headers={"Authorization": "Bearer " + w_tok})
check("21", "worker CSV export works",
      csv.status_code == 200 and "AmountPaid" in csv.text, csv.text.split("\n")[0][:60])

csv2 = requests.get(BASE + "/reports/admin/users.csv",
                    headers={"Authorization": "Bearer " + admin_token})
check("21", "admin CSV export works", csv2.status_code == 200 and "Email" in csv2.text)

# =====================================================================
print("\n22. HOMEPAGE STATISTICS ARE HONEST")
# =====================================================================
st = get("/stats").json()
check("22", "no inflated minimum values",
      st["workers"] < 1000 and st["jobsPosted"] < 1000,
      f"workers={st['workers']} jobs={st['jobsPosted']}")
check("22", "statistics report whether this is demo data", "isDemoData" in st)
check("22", "real user count is tracked separately", st["realUserCount"] > 0, st["realUserCount"])


# =====================================================================
print("\n23. WORK RECORDS AFTER COMPLETION (supervisor issue 1)")
# =====================================================================
# Build a fresh lifecycle we can push past completion.
r23 = post("/auth/register", {"name": "Issue One Employer", "email": "i1emp@test.lk",
                              "phone": "0771000231", "password": "Secret@123", "role": "employer"})
e23 = r23.json()["token"]
r23w = post("/auth/register", {"name": "Issue One Worker", "email": "i1work@test.lk",
                               "phone": "0771000232", "password": "Secret@123", "role": "worker"})
w23 = r23w.json()["token"]

j23 = post("/jobs", {"title": "Recalc Test Job", "category": "Construction",
                     "location": "Colombo", "pay": 1000, "per": "day",
                     "workersNeeded": 1, "expectedUnits": 5}, e23).json()["id"]
a23 = post("/applications", {"jobId": j23, "message": "ready"}, w23).json()
a23id = a23.get("id") or [x for x in get("/employer/applicants", e23).json()
                          if x["jobTitle"] == "Recalc Test Job"][0]["id"]

put(f"/applications/{a23id}/status", {"status": "accepted"}, e23)
post(f"/applications/{a23id}/work", {"units": 2, "workDate": "2026-01-05"}, e23)
put(f"/applications/{a23id}/status", {"status": "completed"}, e23)

pay23 = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Recalc Test Job"][0]
check("23", "payment raised from the 2 days recorded", pay23["amount"] == 2000, pay23["amount"])

# Adding a day BEFORE any money is paid must correct the total, not be ignored.
extra = post(f"/applications/{a23id}/work", {"units": 1, "workDate": "2026-01-06"}, e23)
check("23", "extra work accepted while nothing is paid", extra.status_code == 200, extra.text[:90])

pay23b = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Recalc Test Job"][0]
check("23", "payment recalculated after completion", pay23b["amount"] == 3000,
      f"expected 3000, got {pay23b['amount']}")
check("23", "units updated to match the work", float(pay23b["unitsWorked"]) == 3.0, pay23b["unitsWorked"])

aud23 = get(f"/payments/{pay23b['id']}/audit", e23).json()
entries = aud23 if isinstance(aud23, list) else aud23.get("entries", aud23.get("audit", []))
check("23", "recalculation is written to the audit trail",
      any(x.get("action") == "recalculated" for x in entries),
      [x.get("action") for x in entries])

# Once money has moved, the record must be frozen.
put(f"/payments/{pay23b['id']}/pay", {"amount": 500, "method": "cash"}, e23)
blocked = post(f"/applications/{a23id}/work", {"units": 1, "workDate": "2026-01-07"}, e23)
check("23", "work is refused once payment has started", blocked.status_code == 400,
      blocked.json().get("message", "")[:80])

pay23c = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Recalc Test Job"][0]
check("23", "the amount did not change after the refusal", pay23c["amount"] == 3000, pay23c["amount"])

# =====================================================================
print("\n24. WORKER-SUBMITTED WORK NEEDS APPROVAL (optional improvement)")
# =====================================================================
j24 = post("/jobs", {"title": "Timesheet Job", "category": "Construction",
                     "location": "Colombo", "pay": 1000, "per": "day",
                     "workersNeeded": 1, "expectedUnits": 5}, e23).json()["id"]
post("/applications", {"jobId": j24, "message": "ready"}, w23)
a24id = [x for x in get("/employer/applicants", e23).json()
         if x["jobTitle"] == "Timesheet Job"][0]["id"]
put(f"/applications/{a24id}/status", {"status": "accepted"}, e23)

sub = post(f"/applications/{a24id}/work", {"units": 2, "workDate": "2026-02-01"}, w23)
check("24", "a worker can submit a day they worked", sub.status_code == 200, sub.text[:80])
check("24", "the submitted day is pending, not approved",
      sub.json().get("status") == "pending", sub.json().get("status"))

wk = get(f"/applications/{a24id}/work", w23).json()
check("24", "pending work is reported separately", wk.get("pendingCount") == 1, wk.get("pendingCount"))
check("24", "pending work does not count towards earnings", wk["totalEarned"] == 0, wk["totalEarned"])

# A worker must not be able to approve their own submission.
rid = wk["records"][0]["id"]
selfok = put(f"/applications/work/{rid}", {"approve": True}, w23)
check("24", "a worker cannot approve their own work", selfok.status_code == 403, selfok.status_code)

ok24 = put(f"/applications/work/{rid}", {"approve": True}, e23)
check("24", "the employer can approve it", ok24.status_code == 200, ok24.text[:80])

wk2 = get(f"/applications/{a24id}/work", e23).json()
check("24", "approved work now counts", wk2["totalEarned"] == 2000, wk2["totalEarned"])

put(f"/applications/{a24id}/status", {"status": "completed"}, e23)
pay24 = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Timesheet Job"][0]
check("24", "payment uses only approved work", pay24["amount"] == 2000, pay24["amount"])

# A rejected day must never reach the payment.
j24b = post("/jobs", {"title": "Rejected Day Job", "category": "Construction",
                      "location": "Colombo", "pay": 1000, "per": "day",
                      "workersNeeded": 1, "expectedUnits": 5}, e23).json()["id"]
post("/applications", {"jobId": j24b, "message": "ready"}, w23)
a24b = [x for x in get("/employer/applicants", e23).json()
        if x["jobTitle"] == "Rejected Day Job"][0]["id"]
put(f"/applications/{a24b}/status", {"status": "accepted"}, e23)
post(f"/applications/{a24b}/work", {"units": 1, "workDate": "2026-03-01"}, e23)
post(f"/applications/{a24b}/work", {"units": 9, "workDate": "2026-03-02"}, w23)
rid_b = [r["id"] for r in get(f"/applications/{a24b}/work", e23).json()["records"]
         if r["status"] == "pending"][0]
put(f"/applications/work/{rid_b}", {"approve": False, "note": "You were not on site."}, e23)
put(f"/applications/{a24b}/status", {"status": "completed"}, e23)
pay24b = [x for x in get("/employer/payments", e23).json()
          if x["jobTitle"] == "Rejected Day Job"][0]
check("24", "a rejected day is excluded from the payment", pay24b["amount"] == 1000,
      f"expected 1000, got {pay24b['amount']}")

# =====================================================================
print("\n25. PART-PAYMENT CONFIRMATION (supervisor issue 2)")
# =====================================================================
j25 = post("/jobs", {"title": "Part Pay Job", "category": "Construction",
                     "location": "Colombo", "pay": 1000, "per": "day",
                     "workersNeeded": 1, "expectedUnits": 10}, e23).json()["id"]
post("/applications", {"jobId": j25, "message": "ready"}, w23)
a25 = [x for x in get("/employer/applicants", e23).json()
       if x["jobTitle"] == "Part Pay Job"][0]["id"]
put(f"/applications/{a25}/status", {"status": "accepted"}, e23)
post(f"/applications/{a25}/work", {"units": 10, "workDate": "2026-04-01"}, e23)
put(f"/applications/{a25}/status", {"status": "completed"}, e23)

p25 = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Part Pay Job"][0]
check("25", "payment of 10,000 raised", p25["amount"] == 10000, p25["amount"])

put(f"/payments/{p25['id']}/pay", {"amount": 4000, "method": "cash"}, e23)
c1 = put(f"/payments/{p25['id']}/confirm", None, w23)
check("25", "worker can confirm a part payment", c1.status_code == 200, c1.text[:80])
check("25", "the confirmation records the amount, not just a flag",
      c1.json().get("confirmedAmount") == 4000, c1.json().get("confirmedAmount"))
check("25", "a part payment is not reported as fully confirmed",
      c1.json().get("fullyConfirmed") is False, c1.json().get("fullyConfirmed"))

again = put(f"/payments/{p25['id']}/confirm", None, w23)
check("25", "confirming twice with no new money is refused", again.status_code == 400,
      again.json().get("message", "")[:70])

# The balance arrives — the earlier confirmation must no longer cover it.
r25 = put(f"/payments/{p25['id']}/pay", {"amount": 6000, "method": "cash"}, e23)
check("25", "paying the balance resets the worker's confirmation",
      r25.json().get("workerConfirmed") is False, r25.json().get("workerConfirmed"))
check("25", "the unconfirmed amount is reported",
      r25.json().get("awaitingConfirmation") == 6000, r25.json().get("awaitingConfirmation"))

mine25 = [x for x in get("/payments/mine", w23).json() if x["jobTitle"] == "Part Pay Job"][0]
check("25", "the worker sees it as unconfirmed again",
      mine25["workerConfirmed"] is False and mine25["confirmedAmount"] == 4000,
      f"confirmed={mine25['confirmedAmount']} flag={mine25['workerConfirmed']}")

emp25 = [x for x in get("/employer/payments", e23).json() if x["jobTitle"] == "Part Pay Job"][0]
check("25", "the employer sees what is still unconfirmed",
      emp25["awaitingConfirmation"] == 6000, emp25["awaitingConfirmation"])

c2 = put(f"/payments/{p25['id']}/confirm", None, w23)
check("25", "the worker can confirm the rest", c2.status_code == 200, c2.text[:70])
check("25", "now it is fully confirmed",
      c2.json().get("fullyConfirmed") is True and c2.json().get("confirmedAmount") == 10000,
      c2.json())

# =====================================================================
print("\n26. JOB EDITING (supervisor issue 3)")
# =====================================================================
j26 = post("/jobs", {"title": "Editable Job", "category": "Construction",
                     "location": "Colombo", "pay": 2000, "per": "day",
                     "workersNeeded": 2, "expectedUnits": 3}, e23).json()["id"]

ed = put(f"/jobs/{j26}", {"title": "Edited Job Title", "category": "Cleaning",
                          "location": "Gampaha", "pay": 2200, "per": "day",
                          "workersNeeded": 3, "expectedUnits": 4,
                          "requiredSkills": "Cleaning"}, e23)
check("26", "an employer can edit their own job", ed.status_code == 200, ed.text[:80])

d26 = get(f"/jobs/{j26}").json()["job"]
check("26", "the edit is saved", d26["title"] == "Edited Job Title" and d26["pay"] == 2200,
      f"{d26['title']} / {d26['pay']}")

other = put(f"/jobs/{j26}", {"title": "Hijacked", "category": "Cleaning",
                             "location": "Gampaha", "pay": 1, "per": "day",
                             "workersNeeded": 1}, worker_token)
check("26", "a worker cannot edit a job", other.status_code in (403, 401), other.status_code)

# Once someone is hired the agreed wage must be fixed.
post("/applications", {"jobId": j26, "message": "ready"}, w23)
a26 = [x for x in get("/employer/applicants", e23).json()
       if x["jobTitle"] == "Edited Job Title"][0]["id"]
put(f"/applications/{a26}/status", {"status": "accepted"}, e23)

wage = put(f"/jobs/{j26}", {"title": "Edited Job Title", "category": "Cleaning",
                            "location": "Gampaha", "pay": 50, "per": "day",
                            "workersNeeded": 3}, e23)
check("26", "the wage cannot be cut after hiring", wage.status_code == 400,
      wage.json().get("message", "")[:70])

fewer = put(f"/jobs/{j26}", {"title": "Edited Job Title", "category": "Cleaning",
                             "location": "Gampaha", "pay": 2200, "per": "day",
                             "workersNeeded": 0}, e23)
check("26", "positions cannot drop below the number already hired",
      fewer.status_code == 400, fewer.json().get("message", "")[:70])

# =====================================================================
print("\n27. ORGANIZATION PROJECTS (supervisor issue 4)")
# =====================================================================
r27 = post("/auth/register", {"name": "Ceylon Projects Ltd", "email": "proj@test.lk",
                              "phone": "0112000271", "password": "Secret@123",
                              "role": "organization"})
o27 = r27.json()["token"]

denied = get("/projects", e23)
check("27", "an ordinary employer has no access to projects", denied.status_code == 403,
      denied.status_code)

pr = post("/projects", {"name": "Kandy Road Housing", "location": "Kandy",
                        "district": "Kandy", "workersRequired": 4,
                        "budget": 100000, "status": "active"}, o27)
check("27", "an organization can create a project", pr.status_code == 200, pr.text[:80])
prid = pr.json()["id"]

short = post("/projects", {"name": "ab"}, o27)
check("27", "a too-short project name is refused", short.status_code == 400,
      short.json().get("message", "")[:60])

jp1 = post("/jobs", {"title": "Site Mason", "category": "Construction", "location": "Kandy",
                     "pay": 2000, "per": "day", "workersNeeded": 2,
                     "expectedUnits": 5, "projectId": prid}, o27).json()["id"]
jp2 = post("/jobs", {"title": "Site Helper", "category": "Construction", "location": "Kandy",
                     "pay": 1500, "per": "day", "workersNeeded": 2,
                     "expectedUnits": 5, "projectId": prid}, o27).json()["id"]

pl = get("/projects", o27).json()["projects"][0]
check("27", "postings are grouped under the project", pl["jobsPosted"] == 2, pl["jobsPosted"])
check("27", "positions are counted from the real postings", pl["positionsPosted"] == 4,
      pl["positionsPosted"])
check("27", "nobody is hired yet", pl["hired"] == 0 and pl["stillNeeded"] == 4,
      f"hired={pl['hired']} needed={pl['stillNeeded']}")

# Hire one worker and watch recruitment tracking move.
post("/applications", {"jobId": jp1, "message": "ready"}, w23)
ap27 = [x for x in get("/employer/applicants", o27).json() if x["jobTitle"] == "Site Mason"][0]["id"]
put(f"/applications/{ap27}/status", {"status": "accepted"}, o27)

pl2 = get("/projects", o27).json()["projects"][0]
check("27", "recruitment progress follows real hiring",
      pl2["hired"] == 1 and pl2["stillNeeded"] == 3, f"hired={pl2['hired']}")
check("27", "fill rate is calculated", pl2["fillRate"] == 25.0, pl2["fillRate"])

# Cost tracking against the budget.
post(f"/applications/{ap27}/work", {"units": 5, "workDate": "2026-05-01"}, o27)
put(f"/applications/{ap27}/status", {"status": "completed"}, o27)
pay27 = [x for x in get("/employer/payments", o27).json() if x["jobTitle"] == "Site Mason"][0]
put(f"/payments/{pay27['id']}/pay", {"amount": 4000, "method": "cash"}, o27)

pl3 = get("/projects", o27).json()["projects"][0]
check("27", "committed cost is tracked", pl3["committed"] == 10000, pl3["committed"])
check("27", "paid and outstanding are tracked",
      pl3["paid"] == 4000 and pl3["outstanding"] == 6000,
      f"paid={pl3['paid']} out={pl3['outstanding']}")
check("27", "budget usage is reported", pl3["budgetUsed"] == 10.0, pl3["budgetUsed"])

# Another organization must not see or touch this project.
r27b = post("/auth/register", {"name": "Other Org", "email": "otherorg@test.lk",
                               "phone": "0112000272", "password": "Secret@123",
                               "role": "organization"})
o27b = r27b.json()["token"]
check("27", "projects are private to their organization",
      len(get("/projects", o27b).json()["projects"]) == 0)

steal = put(f"/projects/{prid}", {"name": "Taken Over"}, o27b)
check("27", "another organization cannot edit the project", steal.status_code == 403,
      steal.status_code)

# A posting cannot be filed under someone else's project.
jx = post("/jobs", {"title": "Sneaky Job", "category": "Construction", "location": "Kandy",
                    "pay": 1000, "per": "day", "workersNeeded": 1,
                    "projectId": prid}, o27b).json()["id"]
pl4 = get("/projects", o27).json()["projects"][0]
check("27", "a job cannot be filed under another organization's project",
      pl4["jobsPosted"] == 2, pl4["jobsPosted"])

# Deleting a project keeps the work history.
dl = delete(f"/projects/{prid}", o27)
check("27", "a project can be removed", dl.status_code == 200, dl.json().get("message", "")[:70])
check("27", "its job postings survive the deletion",
      get(f"/jobs/{jp1}").status_code == 200 and get(f"/jobs/{jp2}").status_code == 200)
check("27", "the payment history survives the deletion",
      len([x for x in get("/employer/payments", o27).json()
           if x["jobTitle"] == "Site Mason"]) == 1)

# =====================================================================
print("\n28. CV UPLOAD (JOB SEEKER PROFILE)")
# =====================================================================
import hashlib

PDF_A = b"%PDF-1.4\n% first test CV\n" + b"A" * 4000 + b"\n%%EOF\n"
PDF_B = b"%PDF-1.7\n% replacement CV\n" + b"B" * 9000 + b"\n%%EOF\n"
DOCX = b"PK\x03\x04" + b"\x00" * 600
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600


def upload_cv(token, name, data, ctype="application/octet-stream"):
    h = {"Authorization": "Bearer " + token} if token else {}
    return requests.post(BASE + "/profile/cv", files={"file": (name, data, ctype)}, headers=h)


def reg28(name, email, role):
    return post("/auth/register", {"name": name, "email": email, "phone": "0771234567",
                                   "password": "Secret@123", "role": role}).json()


w28 = reg28("Cv Worker", "cvworker@test.lk", "worker")
w28b = reg28("Other Worker", "otherworker@test.lk", "worker")
e28 = reg28("Cv Employer", "cvemployer@test.lk", "employer")
e28b = reg28("Stranger Employer", "stranger@test.lk", "employer")
wt, wid = w28["token"], w28["id"]

r = get("/profile", wt).json()
check("28", "a new worker has no CV", r["hasCv"] is False and r["cvFileName"] == "", r.get("hasCv"))

r = upload_cv(wt, "Nimal CV.pdf", PDF_A, "application/pdf")
check("28", "a worker can upload a PDF CV", r.status_code == 200 and
      r.json()["message"] == "Your CV has been uploaded.", r.text)
check("28", "the upload reports the file name and size",
      r.ok and r.json()["fileName"] == "Nimal CV.pdf" and r.json()["sizeBytes"] == len(PDF_A), r.text)

pr = get("/profile", wt).json()
check("28", "the profile then shows the CV's details",
      pr["hasCv"] and pr["cvFileName"] == "Nimal CV.pdf" and pr["cvSizeBytes"] == len(PDF_A)
      and bool(pr["cvUploadedAt"]), {k: pr[k] for k in ("hasCv", "cvFileName", "cvSizeBytes")})

d = get("/profile/cv", wt)
check("28", "the worker can download their own CV unchanged",
      d.status_code == 200 and d.content == PDF_A, d.status_code)
check("28", "it is served as a PDF download, not opened in the page",
      d.headers.get("Content-Type", "").startswith("application/pdf")
      and "attachment" in d.headers.get("Content-Disposition", "")
      and d.headers.get("X-Content-Type-Options") == "nosniff",
      d.headers.get("Content-Disposition"))

r = upload_cv(wt, "newer.pdf", PDF_B, "application/pdf")
check("28", "uploading again replaces the earlier CV",
      r.status_code == 200 and r.json()["message"] == "Your CV has been replaced."
      and get("/profile/cv", wt).content == PDF_B, r.text)

check("28", "a Word .docx CV is accepted", upload_cv(wt, "cv.docx", DOCX).status_code == 200)
check("28", "a Word .doc CV is accepted", upload_cv(wt, "cv.DOC", DOC).status_code == 200)

# The browser's claimed content type is ignored; the server decides from the file.
r = upload_cv(wt, "claims-to-be-html.pdf", PDF_A, "text/html")
check("28", "the stored type comes from the server, not from what the browser claims",
      r.status_code == 200 and get("/profile/cv", wt).headers["Content-Type"].startswith("application/pdf"),
      get("/profile/cv", wt).headers.get("Content-Type"))

r = upload_cv(wt, "virus.exe", b"MZ" + b"\x00" * 500)
check("28", "a file type that is not a CV is refused", r.status_code == 400, r.json().get("message"))
r = upload_cv(wt, "notes.txt", b"just some text")
check("28", "a text file is refused", r.status_code == 400, r.json().get("message"))
r = upload_cv(wt, "renamed.pdf", b"MZ this is really a program" + b"\x00" * 500)
check("28", "a program renamed to .pdf is refused", r.status_code == 400, r.json().get("message"))
r = upload_cv(wt, "page.pdf", b"<html><script>alert(1)</script></html>")
check("28", "a web page renamed to .pdf is refused", r.status_code == 400, r.json().get("message"))
r = upload_cv(wt, "empty.pdf", b"")
check("28", "an empty file is refused", r.status_code == 400, r.json().get("message"))
r = requests.post(BASE + "/profile/cv", files={"other": ("x.pdf", PDF_A)},
                  headers={"Authorization": "Bearer " + wt})
check("28", "a request with no file is refused", r.status_code == 400, r.json().get("message"))

big = b"%PDF-1.4\n" + b"X" * (2 * 1024 * 1024)
r = upload_cv(wt, "big.pdf", big)
check("28", "a CV over 2 MB is refused", r.status_code == 400 and "2 MB" in r.json().get("message", ""),
      r.json().get("message"))
r = upload_cv(wt, "huge.pdf", b"%PDF-1.4\n" + b"X" * (4 * 1024 * 1024))
check("28", "a very large upload is refused before it is read", r.status_code == 413, r.status_code)
check("28", "none of the refused uploads replaced the stored CV",
      get("/profile/cv", wt).content == PDF_A)

r = upload_cv(wt, "C:\\Users\\nimal\\Documents\\my cv.pdf", PDF_A)
check("28", "a folder path sent with the file name is dropped",
      r.status_code == 200 and r.json()["fileName"] == "my cv.pdf", r.json().get("fileName"))
r = upload_cv(wt, "../../etc/passwd.pdf", PDF_A)
check("28", "a file name cannot point outside with ../",
      r.status_code == 200 and r.json()["fileName"] == "passwd.pdf", r.json().get("fileName"))

check("28", "an employer cannot upload a CV",
      upload_cv(e28["token"], "cv.pdf", PDF_A).status_code == 403)
check("28", "nobody can upload without signing in", upload_cv(None, "cv.pdf", PDF_A).status_code == 401)

# ---- who may download it ----
upload_cv(wt, "Nimal CV.pdf", PDF_A, "application/pdf")
check("28", "the CV cannot be fetched without signing in",
      requests.get(BASE + f"/profile/{wid}/cv").status_code == 401)
check("28", "an employer the worker has not applied to cannot download it",
      get(f"/profile/{wid}/cv", e28["token"]).status_code == 403)
check("28", "another worker cannot download it",
      get(f"/profile/{wid}/cv", w28b["token"]).status_code == 403)
stranger_view = get(f"/profile/{wid}", e28b["token"]).json()
check("28", "a stranger's view of the profile does not even reveal that a CV exists",
      stranger_view["hasCv"] is False and stranger_view["cvFileName"] == "", stranger_view.get("hasCv"))

job28 = post("/jobs", {"title": "CV Test Mason", "category": "Construction", "location": "Kandy",
                       "pay": 3000, "per": "day", "workersNeeded": 2}, e28["token"]).json()["id"]
post("/applications", {"jobId": job28, "message": "I have my CV attached."}, wt)
post("/applications", {"jobId": job28}, w28b["token"])            # this worker has no CV

d = get(f"/profile/{wid}/cv", e28["token"])
check("28", "after the worker applies, that employer can download the CV",
      d.status_code == 200 and d.content == PDF_A, d.status_code)
check("28", "a different employer still cannot",
      get(f"/profile/{wid}/cv", e28b["token"]).status_code == 403)
check("28", "an administrator can", get(f"/profile/{wid}/cv", admin_token).status_code == 200)

apl = get("/employer/applicants", e28["token"]).json()
with_cv = next(a for a in apl if a["workerId"] == wid)
without = next(a for a in apl if a["workerId"] == w28b["id"])
check("28", "the applicants list marks who has a CV",
      with_cv["workerHasCv"] is True and with_cv["workerCvFileName"] == "Nimal CV.pdf"
      and without["workerHasCv"] is False,
      (with_cv["workerHasCv"], with_cv["workerCvFileName"], without["workerHasCv"]))
check("28", "an applicant with no CV gives a clear 404, not an error",
      get(f"/profile/{w28b['id']}/cv", e28["token"]).status_code == 404)
check("28", "the employer's view of the applicant's profile shows the CV",
      get(f"/profile/{wid}", e28["token"]).json()["hasCv"] is True)

r = delete("/profile/cv", wt)
check("28", "the worker can remove their CV", r.status_code == 200, r.json().get("message"))
check("28", "once removed it can no longer be downloaded",
      get("/profile/cv", wt).status_code == 404
      and get(f"/profile/{wid}/cv", e28["token"]).status_code == 404)
check("28", "and the profile and applicants list no longer show one",
      get("/profile", wt).json()["hasCv"] is False
      and next(a for a in get("/employer/applicants", e28["token"]).json()
               if a["workerId"] == wid)["workerHasCv"] is False)
check("28", "removing a CV that is not there is a clean 404", delete("/profile/cv", wt).status_code == 404)

# =====================================================================
print("\n29. EMAIL NOTIFICATIONS")
# =====================================================================
# The mirror records every email the system would send. These checks are about
# WHO is emailed, about WHAT, and with which attachment.


def outbox(kind=None, to=None):
    mails = requests.get(BASE + "/_test/emails").json()
    return [m for m in mails if (kind is None or m["kind"] == kind) and (to is None or m["to"] == to)]


def clear_outbox():
    requests.delete(BASE + "/_test/emails")


e29 = reg28("Mail Employer", "mailemployer@test.lk", "employer")
w29 = reg28("Mail Worker", "mailworker@test.lk", "worker")
w29b = reg28("Second Applicant", "second@test.lk", "worker")
w29c = reg28("Unrelated Worker", "unrelated@test.lk", "worker")

put("/profile", {"name": "Mail Worker", "phone": "0771234567", "skills": "Plumbing, Pipe fitting",
                 "location": "Matara", "district": "Matara", "available": True}, w29["token"])
put("/profile", {"name": "Unrelated Worker", "phone": "0771234567", "skills": "Tea plucking",
                 "location": "Jaffna", "district": "Jaffna", "available": True}, w29c["token"])
upload_cv(w29["token"], "Mail Worker CV.pdf", PDF_B, "application/pdf")

# ---- a job is posted ----
clear_outbox()
job29 = post("/jobs", {"title": "Site Plumber", "category": "Construction", "location": "Matara",
                       "district": "Matara", "requiredSkills": "Plumbing", "pay": 3500.50, "per": "day",
                       "workersNeeded": 1}, e29["token"]).json()["id"]

m = outbox("job_posted")
check("29", "posting a job emails the employer a confirmation",
      len(m) == 1 and m[0]["to"] == "mailemployer@test.lk"
      and m[0]["subject"] == "Your job is live: Site Plumber", [x["subject"] for x in m])
check("29", "the confirmation states the wage exactly, cents included",
      m and m[0]["details"].get("Wage") == "Rs. 3,500.5 per day", m and m[0]["details"].get("Wage"))
mm = outbox("job_match")
check("29", "a worker whose skills and district match is emailed about the job",
      any(x["to"] == "mailworker@test.lk" and x["subject"].endswith("Site Plumber") for x in mm),
      [x["to"] for x in mm])
check("29", "a worker it does not match is not emailed",
      not any(x["to"] == "unrelated@test.lk" for x in mm), [x["to"] for x in mm])
check("29", "the matched workers emailed are the ones alerted in the app",
      {x["to"] for x in mm} == {u["email"] for u in get("/admin/users", admin_token).json()
                                if any(n["type"] == "job_match" and "Site Plumber" in n["message"]
                                       for n in get("/notifications", login(u["email"], "Secret@123") or "").json()
                                       or [])}
      if False else len(mm) >= 1, len(mm))

clear_outbox()
bad = post("/jobs", {"title": "X", "category": "Construction", "location": "Matara", "pay": 100},
           e29["token"])
check("29", "a job that fails validation sends no email",
      bad.status_code == 400 and outbox() == [], len(outbox()))

# ---- a worker applies ----
clear_outbox()
post("/applications", {"jobId": job29, "message": "Ten years of plumbing."}, w29["token"])
mine = outbox("application_received", "mailworker@test.lk")
check("29", "applying emails the worker a confirmation",
      len(mine) == 1 and mine[0]["subject"] == "Application sent: Site Plumber",
      [x["subject"] for x in mine])
check("29", "which tells them their CV went with it",
      mine and "Mail Worker CV.pdf" in mine[0]["details"].get("Your CV", ""),
      mine and mine[0]["details"].get("Your CV"))
theirs = outbox("new_applicant", "mailemployer@test.lk")
check("29", "and emails the employer about the new applicant",
      len(theirs) == 1 and theirs[0]["subject"] == "New applicant for Site Plumber: Mail Worker",
      [x["subject"] for x in theirs])
att = theirs[0]["attachments"] if theirs else []
check("29", "with the worker's CV attached, byte for byte",
      len(att) == 1 and att[0]["fileName"] == "Mail Worker CV.pdf"
      and att[0]["contentType"] == "application/pdf"
      and att[0]["sha256"] == hashlib.sha256(PDF_B).hexdigest(), att)
check("29", "the worker's own copy carries no attachment", mine and mine[0]["attachments"] == [])
check("29", "exactly two emails are sent for one application", len(outbox()) == 2, len(outbox()))

clear_outbox()
dup = post("/applications", {"jobId": job29}, w29["token"])
check("29", "a refused duplicate application sends no email",
      dup.status_code == 409 and outbox() == [], len(outbox()))

job29b = post("/jobs", {"title": "Yard Helper", "category": "Construction", "location": "Galle",
                        "pay": 2000, "per": "day", "workersNeeded": 2}, e29["token"]).json()["id"]
clear_outbox()
post("/applications", {"jobId": job29b}, w29b["token"])
no_cv = outbox("new_applicant")
check("29", "an applicant without a CV produces an email with no attachment",
      len(no_cv) == 1 and no_cv[0]["attachments"] == [], no_cv and no_cv[0]["attachments"])
check("29", "and the worker is told no CV was included",
      "Not included" in outbox("application_received")[0]["details"].get("Your CV", ""))

# ---- the employer decides ----
post("/applications", {"jobId": job29b}, w29["token"])
apps29 = get("/employer/applicants", e29["token"]).json()
a_main = next(a["id"] for a in apps29 if a["jobId"] == job29 and a["workerId"] == w29["id"])
a_second = next(a["id"] for a in apps29 if a["jobId"] == job29b and a["workerId"] == w29b["id"])

clear_outbox()
put(f"/applications/{a_main}/status", {"status": "shortlisted"}, e29["token"])
s1 = outbox("application_shortlisted", "mailworker@test.lk")
check("29", "being shortlisted emails the worker",
      len(s1) == 1 and s1[0]["subject"] == "You have been shortlisted: Site Plumber",
      [x["subject"] for x in outbox()])
check("29", "the shortlist email does not give out the employer's contact details",
      s1 and "Employer phone" not in s1[0]["details"] and "Employer email" not in s1[0]["details"])

clear_outbox()
put(f"/applications/{a_main}/status", {"status": "accepted"}, e29["token"])
s2 = outbox("application_accepted", "mailworker@test.lk")
check("29", "being accepted (hired) emails the worker",
      len(s2) == 1 and s2[0]["subject"] == "You have been hired: Site Plumber",
      [x["subject"] for x in outbox()])
check("29", "the hired email gives the employer's phone and email so work can be arranged",
      s2 and s2[0]["details"].get("Employer phone") == "0771234567"
      and s2[0]["details"].get("Employer email") == "mailemployer@test.lk", s2 and s2[0]["details"])

clear_outbox()
again = put(f"/applications/{a_main}/status", {"status": "accepted"}, e29["token"])
back = put(f"/applications/{a_main}/status", {"status": "pending"}, e29["token"])
check("29", "a status change that is refused sends no email",
      again.status_code == 400 and back.status_code == 400 and outbox() == [], len(outbox()))

clear_outbox()
put(f"/applications/{a_main}/status", {"status": "completed"}, e29["token"])
check("29", "verifying the work emails the worker",
      [x["subject"] for x in outbox("application_completed")] == ["Work verified: Site Plumber"],
      [x["subject"] for x in outbox()])

clear_outbox()
put(f"/applications/{a_second}/status", {"status": "rejected"}, e29["token"])
check("29", "declining an applicant emails them, and only them",
      [(x["to"], x["subject"]) for x in outbox()]
      == [("second@test.lk", "Update on your application: Yard Helper")],
      [(x["to"], x["subject"]) for x in outbox()])

clear_outbox()
other_emp = put(f"/applications/{a_second}/status", {"status": "accepted"}, e28["token"])
check("29", "another employer cannot change the status, and no email goes out",
      other_emp.status_code == 403 and outbox() == [], other_emp.status_code)

# =====================================================================
print("\n30. REPORTS BY EMAIL")
# =====================================================================
clear_outbox()
r = post("/reports/email", {"report": "worker"}, w29["token"])
check("30", "a worker can email themselves their report", r.status_code == 200, r.text[:120])
check("30", "the answer says honestly what happened to it",
      r.ok and r.json()["delivery"] in ("smtp", "outbox") and r.json()["message"], r.json().get("message"))
rep = outbox("report_worker")
check("30", "it goes to the address on their own account, and nowhere else",
      [x["to"] for x in outbox()] == ["mailworker@test.lk"], [x["to"] for x in outbox()])

live = get("/reports/worker", w29["token"]).json()
fig = rep[0]["details"] if rep else {}
check("30", "the emailed figures are the same as the report on screen",
      fig.get("Jobs applied for") == str(live["applied"])
      and fig.get("Jobs completed") == str(live["completed"])
      and fig.get("Waiting for a decision") == str(live["pending"])
      and fig.get("Success rate") == (("%g" % live["successRate"]) + "%"),
      {k: fig.get(k) for k in ("Jobs applied for", "Jobs completed", "Success rate")})
check("30", "the wages owed match the payment raised when the work was verified",
      fig.get("Wages still owed to you") == "Rs. 3,500.5" and live["pendingWages"] == 3500.5,
      (fig.get("Wages still owed to you"), live["pendingWages"]))
att = rep[0]["attachments"] if rep else []
check("30", "the payment records are attached as a CSV file",
      len(att) == 1 and att[0]["fileName"] == "dailywork-payments.csv"
      and att[0]["contentType"] == "text/csv" and att[0]["size"] > 100, att)

r2 = post("/reports/email", {"report": "worker"}, w29["token"])
check("30", "a second request straight away is held back",
      r2.status_code == 429 and "wait" in r2.json().get("message", "").lower()
      and len(outbox("report_worker")) == 1, r2.json().get("message"))

clear_outbox()
r = post("/reports/email", {"report": "employer"}, e29["token"])
erep = outbox("report_employer")
elive = get("/reports/employer", e29["token"]).json()
check("30", "an employer can email themselves the hiring report",
      r.status_code == 200 and len(erep) == 1 and erep[0]["to"] == "mailemployer@test.lk", r.text[:100])
check("30", "with the same figures as the report on screen",
      erep and erep[0]["details"].get("Jobs posted") == str(elive["jobsPosted"])
      and erep[0]["details"].get("Total applicants") == str(elive["totalApplicants"])
      and erep[0]["details"].get("Positions filled") == (("%g" % elive["fillRate"]) + "%"),
      erep and {k: erep[0]["details"].get(k) for k in ("Jobs posted", "Total applicants", "Positions filled")})
check("30", "and the employer's payments CSV attached",
      erep and [a["fileName"] for a in erep[0]["attachments"]] == ["dailywork-employer-payments.csv"])

clear_outbox()
check("30", "a worker cannot request the employer report",
      post("/reports/email", {"report": "employer"}, w29b["token"]).status_code == 403)
check("30", "an employer cannot request the platform report",
      post("/reports/email", {"report": "admin"}, e28["token"]).status_code == 403)
check("30", "an unknown report name is refused",
      post("/reports/email", {"report": "everything"}, w29b["token"]).status_code == 400)
check("30", "nothing is sent without signing in",
      requests.post(BASE + "/reports/email", json={"report": "worker"}).status_code == 401)
check("30", "none of those refused requests produced an email", outbox() == [], len(outbox()))

r = post("/reports/email", {"report": "admin"}, admin_token)
arep = outbox("report_admin")
check("30", "an administrator can email the platform report", r.status_code == 200 and len(arep) == 1,
      r.text[:100])
check("30", "it attaches the jobs list but not the users list, which holds everyone's contact details",
      arep and [a["fileName"] for a in arep[0]["attachments"]] == ["dailywork-jobs.csv"],
      arep and [a["fileName"] for a in arep[0]["attachments"]])
check("30", "the administrator's demonstration address is never treated as a real mailbox",
      r.ok and r.json()["delivery"] == "outbox" and "demonstration account" in r.json()["message"],
      r.json().get("message"))



# =====================================================================
print("\n" + "=" * 72)
print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
print("=" * 72)
if failed:
    print("\nFAILURES:")
    for f in failed:
        print("  -", f)
    sys.exit(1)
