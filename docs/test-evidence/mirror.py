"""
TEST HARNESS ONLY — not part of the delivered project.

Implements the same HTTP contract as the ASP.NET Core backend (identical routes,
camelCase JSON, status codes, error messages and business rules) so the real
frontend can be driven end to end in this environment, where the .NET SDK is
not available.

The business rules here are transcribed from the C# controllers so that a test
passing against this server means the frontend and the API contract agree.
"""
import sys, json, datetime, hashlib, base64, hmac, re, os
from flask import Flask, request, jsonify, send_from_directory, Response

WWWROOT = sys.argv[1]
app = Flask(__name__, static_folder=None)
SECRET = b"test-secret"

DB = {"users": [], "jobs": [], "apps": [], "payments": [], "audits": [], "projects": [],
      "work": [], "ratings": [], "notes": [], "categories": [], "messages": [],
      "cvs": {},        # userId -> the worker's CV (mirrors the CvDocuments table)
      "emails": [],     # every email the system would send (mirrors EmailQueue)
      "next": {k: 1 for k in ["user", "job", "app", "payment", "audit", "work",
                              "rating", "note", "category", "message", "project"]}}


def nid(k):
    v = DB["next"][k]; DB["next"][k] += 1; return v


def now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()


def make_token(u):
    payload = base64.urlsafe_b64encode(json.dumps(
        {"id": u["id"], "role": u["role"], "stamp": u.get("securityStamp", "0")}).encode()).decode()
    sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return payload + "." + sig


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    tok = auth[7:]
    if "." not in tok:
        return None
    payload, sig = tok.rsplit(".", 1)
    if hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16] != sig:
        return None
    try:
        c = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    u = next((x for x in DB["users"] if x["id"] == c["id"]), None)
    if not u or not u.get("isActive", True):
        return None
    # security stamp check: a changed stamp invalidates the token
    if str(u.get("securityStamp", "0")) != str(c.get("stamp", "0")):
        return None
    return u


def role_in(u, *roles):
    return u is not None and u["role"] in roles


def note(uid, ntype, title, msg):
    DB["notes"].append({"id": nid("note"), "userId": uid, "type": ntype, "title": title,
                        "message": msg, "isRead": False, "createdAt": now()})


def user_by_id(i):
    return next((u for u in DB["users"] if u["id"] == i), None)


def avg_stars(uid):
    v = [r["stars"] for r in DB["ratings"] if r["subjectId"] == uid]
    return round(sum(v) / len(v), 1) if v else 0


def money(x):
    return round(float(x), 2)


# =====================================================================
# Email (mirrors EmailQueue.cs, EmailDispatcher.cs and EmailTemplates.cs)
#
# This test server never sends anything. Each message is recorded in
# DB["emails"] together with what the C# service would do with it, so the
# tests can check who is emailed, about what, and with which attachment.
#
#   DW_MIRROR_MAIL    off | outbox | smtp   which EmailDelivery mode to act as
#   DW_MIRROR_OUTBOX  1 | 0                 whether an outbox folder is configured
# =====================================================================
MAIL_MODE = os.environ.get("DW_MIRROR_MAIL", "outbox")
MAIL_OUTBOX = os.environ.get("DW_MIRROR_OUTBOX", "1") == "1"
DEMO_DOMAIN = "@dailywork.lk"
LAST_REPORT = {}


def is_demo(email):
    return (email or "").strip().lower().endswith(DEMO_DOMAIN)


def delivery_for(email):
    """EmailQueue.DeliveryFor: demonstration accounts never get real email."""
    if MAIL_MODE == "smtp" and is_demo(email):
        return "outbox" if MAIL_OUTBOX else "off"
    return MAIL_MODE


def rs(x):
    """EmailTemplates.Money: thousands separators, cents only when there are any."""
    v = round(float(x), 2)
    return "Rs. " + (f"{v:,.2f}".rstrip("0").rstrip("."))


def queue_email(kind, to, to_name, subject, details=None, attachments=None):
    """EmailQueue.Enqueue. Returns False when the message is not queued."""
    if not to or "@" not in to:
        return False
    if MAIL_MODE == "off":
        return False
    DB["emails"].append({
        "kind": kind, "to": to, "toName": to_name, "subject": subject,
        "delivery": delivery_for(to),          # "off" here = dropped by the dispatcher
        "details": {k: v for k, v in (details or []) if str(v).strip()},
        "attachments": [{"fileName": a["fileName"], "contentType": a["contentType"],
                         "size": len(a["data"]),
                         "sha256": hashlib.sha256(a["data"]).hexdigest()}
                        for a in (attachments or [])],
        "createdAt": now()})
    return True


def place(j):
    d = j.get("district") or ""
    return j["location"] if not d or d.lower() == j["location"].lower() else j["location"] + ", " + d


def pay_text(j):
    return rs(j["pay"]) + " per " + j["per"]


def mail_application(worker, j):
    """A worker applied: confirmation to them, and the applicant (with CV) to the employer."""
    emp = user_by_id(j["employerId"])
    cv = DB["cvs"].get(worker["id"])
    queue_email("application_received", worker["email"], worker["name"],
                "Application sent: " + j["title"],
                [("Job", j["title"]), ("Employer", emp["name"] if emp else "the employer"),
                 ("Location", place(j)), ("Wage", pay_text(j)),
                 ("Your CV", "Included with your application (" + cv["fileName"] + ")" if cv
                  else "Not included. You have no CV on your profile yet - you can add one under My Profile.")])
    if emp and emp.get("isActive", True):
        queue_email("new_applicant", emp["email"], emp["name"],
                    "New applicant for " + j["title"] + ": " + worker["name"],
                    [("Applicant", worker["name"]), ("Phone", worker["phone"]),
                     ("Email", worker["email"]), ("Skills", worker.get("skills", ""))],
                    [cv] if cv else [])


STATUS_SUBJECTS = {"shortlisted": "You have been shortlisted: ", "accepted": "You have been hired: ",
                   "rejected": "Update on your application: ", "completed": "Work verified: "}


def mail_status(a, j, target):
    """The employer decided: the worker is told by email as well as in the app."""
    worker = user_by_id(a["workerId"])
    if not worker or not worker.get("isActive", True) or target not in STATUS_SUBJECTS:
        return
    emp = user_by_id(j["employerId"]) or {}
    details = [("Job", j["title"]), ("Employer", emp.get("name", "the employer")),
               ("Location", place(j)), ("Wage", pay_text(j))]
    if target == "accepted":       # contact details only once the worker is hired
        details += [("Employer phone", emp.get("phone", "")), ("Employer email", emp.get("email", ""))]
    queue_email("application_" + target, worker["email"], worker["name"],
                STATUS_SUBJECTS[target] + j["title"], details)


def mail_job_posted(j, matched_workers):
    emp = user_by_id(j["employerId"])
    for w in matched_workers:
        if w.get("isActive", True):
            queue_email("job_match", w["email"], w["name"],
                        "New job that matches your profile: " + j["title"],
                        [("Job", j["title"]), ("Employer", emp["name"] if emp else "An employer"),
                         ("Location", place(j)), ("Wage", pay_text(j))])
    if emp:
        queue_email("job_posted", emp["email"], emp["name"], "Your job is live: " + j["title"],
                    [("Job", j["title"]), ("Category", j["category"]), ("Location", place(j)),
                     ("Wage", pay_text(j)), ("Workers needed", str(j["workersNeeded"])),
                     ("Workers told", str(len(matched_workers)))])


# =====================================================================
# CV rules (mirrors CvRules.cs)
# =====================================================================
CV_MAX_BYTES = 2 * 1024 * 1024
CV_MAX_REQUEST = 3 * 1024 * 1024
CV_TYPES = {".pdf": "application/pdf", ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
CV_SIGNATURES = {".pdf": b"%PDF", ".docx": b"PK\x03\x04", ".doc": b"\xd0\xcf\x11\xe0"}
CV_TYPES_TEXT = "PDF or Word document (.pdf, .doc or .docx)"


def safe_file_name(raw):
    name = (raw or "").replace("\\", "/").split("/")[-1].strip()
    name = "".join(c for c in name if c.isprintable() and c not in '"<>:|?*;').strip()
    stem, ext = os.path.splitext(name)
    stem = stem.strip() or "cv"
    return stem[:80].strip() + ext.lower()


# =====================================================================
# Seed (mirrors DbSeeder.cs)
# =====================================================================
def seed():
    for i, (name, icon) in enumerate([
            ("Construction", "fa-helmet-safety"), ("Agriculture", "fa-seedling"),
            ("Manufacturing", "fa-industry"), ("Transportation", "fa-truck"),
            ("Domestic Services", "fa-house"), ("Cleaning", "fa-broom"),
            ("Security", "fa-shield-halved"), ("Hospitality", "fa-utensils")], start=1):
        DB["categories"].append({"id": nid("category"), "name": name, "description": "",
                                 "icon": icon, "sortOrder": i, "isActive": True,
                                 "createdAt": now()})

    def mkuser(name, email, phone, role, **kw):
        u = {"id": nid("user"), "name": name, "email": email, "phone": phone, "role": role,
             "pw": hash_pw(kw.pop("password", "Password@123")), "createdAt": now(),
             "isActive": True, "securityStamp": "1",
             "skills": "", "location": "", "district": "", "bio": "",
             "experience": "", "experienceYears": 0, "certifications": "", "available": True,
             "verificationStatus": "unverified", "organizationName": "",
             "registrationNumber": "", "organizationAddress": "", "organizationWebsite": "",
             "verificationNotes": "", "verificationDecisionNote": "",
             "verificationRequestedAt": None, "verifiedAt": None}
        u.update(kw)
        DB["users"].append(u)
        return u

    admin = mkuser("System Administrator", "admin@dailywork.lk", "0770000000", "admin",
                   district="Colombo", password="Admin@12345")

    worker = mkuser("Nimal Perera", "worker@dailywork.lk", "0777654321", "worker",
                    skills="Masonry, Painting, Construction", location="Colombo",
                    district="Colombo", experienceYears=8,
                    experience="Eight years on housing and commercial sites.",
                    certifications="NVQ Level 3 Masonry")

    mkuser("Sunil Bandara", "sunil@dailywork.lk", "0771112222", "worker",
           skills="Driving, Delivery, Loading", location="Gampaha", district="Gampaha",
           experienceYears=5)
    mkuser("Kamala Silva", "kamala@dailywork.lk", "0773334444", "worker",
           skills="Cleaning, Housekeeping", location="Colombo", district="Colombo",
           experienceYears=3)

    emps = {}
    for n, mail, phone, district in [
            ("Kasun Fernando", "employer@dailywork.lk", "0771234567", "Colombo"),
            ("Lanka Logistics", "logistics@dailywork.lk", "0112345001", "Gampaha"),
            ("CleanCo", "cleanco@dailywork.lk", "0112345002", "Colombo"),
            ("Green Farms", "farms@dailywork.lk", "0112345003", "Kurunegala"),
            ("QuickMove", "quickmove@dailywork.lk", "0112345004", "Negombo"),
            ("BuildRight", "buildright@dailywork.lk", "0112345005", "Kandy"),
            ("SafeGuard", "safeguard@dailywork.lk", "0112345006", "Colombo"),
            ("HomeCare", "homecare@dailywork.lk", "0112345007", "Negombo"),
            ("ColorPro", "colorpro@dailywork.lk", "0112345008", "Galle"),
            ("Hill Estates", "hill@dailywork.lk", "0112345009", "Nuwara Eliya"),
            ("Pettah Traders", "pettah@dailywork.lk", "0112345010", "Colombo"),
            ("GarmentPlus", "garment@dailywork.lk", "0112345011", "Katunayake")]:
        emps[n] = mkuser(n, mail, phone, "employer", district=district, location=district)["id"]

    org = mkuser("Ceylon Infrastructure (Pvt) Ltd", "organization@dailywork.lk", "0112345020",
                 "organization", district="Colombo", location="Colombo",
                 organizationName="Ceylon Infrastructure (Pvt) Ltd",
                 registrationNumber="PV-00123456",
                 organizationAddress="42 Galle Road, Colombo 03",
                 verificationStatus="verified", verifiedAt=now())

    mkuser("Lanka Agro Services", "agro@dailywork.lk", "0112345021", "organization",
           district="Kurunegala", location="Kurunegala",
           organizationName="Lanka Agro Services", registrationNumber="PV-00987654",
           organizationAddress="118 Kandy Road, Kurunegala",
           verificationStatus="pending", verificationRequestedAt=now(),
           verificationNotes="Registered agricultural labour supplier since 2019.")

    rows = [
        ("Construction Helper", "Construction", "Colombo", "Colombo", 2500, "day", True, "Kasun Fernando", "Construction, Masonry", 1),
        ("Warehouse Worker", "Manufacturing", "Gampaha", "Gampaha", 1900, "day", False, "Lanka Logistics", "Loading, Warehouse", 1),
        ("Office Cleaner", "Cleaning", "Colombo", "Colombo", 1500, "day", False, "CleanCo", "Cleaning, Housekeeping", 1),
        ("Farm Worker", "Agriculture", "Kurunegala", "Kurunegala", 1700, "day", False, "Green Farms", "Farming, Agriculture", 1),
        ("Delivery Assistant", "Transportation", "Negombo", "Gampaha", 2000, "day", True, "QuickMove", "Delivery, Loading, Driving", 1),
        ("Experienced Mason", "Construction", "Kandy", "Kandy", 3200, "day", False, "BuildRight", "Masonry, Construction", 2),
        ("Security Guard (Night)", "Security", "Colombo", "Colombo", 2200, "shift", False, "SafeGuard", "Security", 1),
        ("Housekeeper", "Domestic Services", "Negombo", "Gampaha", 1600, "day", False, "HomeCare", "Housekeeping, Cleaning", 1),
        ("Painter", "Construction", "Galle", "Galle", 2800, "day", True, "ColorPro", "Painting", 1),
        ("Tea Plucker", "Agriculture", "Nuwara Eliya", "Nuwara Eliya", 1400, "day", False, "Hill Estates", "Farming, Agriculture", 5),
        ("Loading Helper", "Transportation", "Colombo", "Colombo", 1800, "day", False, "Pettah Traders", "Loading", 1),
        ("Machine Operator", "Manufacturing", "Katunayake", "Gampaha", 2600, "day", False, "GarmentPlus", "Manufacturing, Machine operation", 1),
    ]
    for t, c, loc, dist, pay, per, urgent, emp, skills, workers in rows:
        DB["jobs"].append({"id": nid("job"), "title": t, "category": c, "location": loc,
                           "district": dist, "pay": pay, "per": per, "urgent": urgent,
                           "status": "open", "description": "", "requiredSkills": skills,
                           "workersNeeded": workers, "expectedUnits": 7,
                           "startDate": None, "endDate": None,
                           "employerId": emps[emp], "createdAt": now(), "updatedAt": None})

    DB["jobs"].append({"id": nid("job"), "title": "Site Supervisor Support",
                       "category": "Construction", "location": "Colombo", "district": "Colombo",
                       "pay": 3000, "per": "day", "urgent": False, "status": "open",
                       "description": "", "requiredSkills": "Construction, Masonry",
                       "workersNeeded": 3, "expectedUnits": 30, "startDate": None,
                       "endDate": None, "employerId": org["id"], "createdAt": now(),
                       "updatedAt": None})

    note(worker["id"], "system", "Welcome to DailyWork",
         "Your profile is set up. Check your recommended jobs to find work that suits your skills.")


# =====================================================================
# Auth
# =====================================================================
LOGIN_FAILS = {}


@app.post("/api/auth/register")
def register():
    d = request.get_json(force=True)
    if d.get("role") not in ("worker", "employer", "organization"):
        return jsonify(message="Admin accounts cannot be self-registered."), 400
    name = (d.get("name") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter your full name."), 400
    email = (d.get("email") or "").strip().lower()
    if "@" not in email or len(email) < 5:
        return jsonify(message="Please enter a valid email address."), 400
    phone = (d.get("phone") or "").strip()
    digits = sum(ch.isdigit() for ch in phone)
    if digits < 9 or digits > 15:
        return jsonify(message="Please enter a valid phone number."), 400

    pw = d.get("password") or ""
    if len(pw) < 8:
        return jsonify(message="Password must be at least 8 characters long."), 400
    if not any(ch.isalpha() for ch in pw):
        return jsonify(message="Password must contain at least one letter."), 400
    if not any(ch.isdigit() for ch in pw):
        return jsonify(message="Password must contain at least one number."), 400
    if pw.lower() in ("password", "12345678", "password1", "dailywork", "admin123"):
        return jsonify(message="That password is too easy to guess. Please choose another one."), 400

    if any(u["email"] == email for u in DB["users"]):
        return jsonify(message="An account with this email already exists."), 409

    u = {"id": nid("user"), "name": name, "email": email, "phone": phone,
         "role": d["role"], "pw": hash_pw(pw), "createdAt": now(), "isActive": True,
         "securityStamp": "1", "skills": "", "location": "", "district": "", "bio": "",
         "experience": "", "experienceYears": 0, "certifications": "", "available": True,
         "verificationStatus": "unverified",
         "organizationName": name if d["role"] == "organization" else "",
         "registrationNumber": "", "organizationAddress": "", "organizationWebsite": "",
         "verificationNotes": "", "verificationDecisionNote": "",
         "verificationRequestedAt": None, "verifiedAt": None}
    DB["users"].append(u)
    note(u["id"], "system", "Welcome to DailyWork", "Add your skills to your profile.")
    return jsonify(id=u["id"], name=u["name"], email=email, role=u["role"],
                   verificationStatus=u["verificationStatus"], token=make_token(u))


@app.post("/api/auth/login")
def login():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip().lower()
    key = email
    fails = LOGIN_FAILS.get(key, 0)
    if fails >= 5:
        return jsonify(message="Too many failed login attempts. Please try again in 15 minute(s)."), 429

    u = next((x for x in DB["users"] if x["email"] == email
              and x["pw"] == hash_pw(d.get("password") or "")), None)
    if not u:
        LOGIN_FAILS[key] = fails + 1
        return jsonify(message="Invalid email or password."), 401
    if not u.get("isActive", True):
        return jsonify(message="This account has been deactivated. Please contact support."), 401

    LOGIN_FAILS.pop(key, None)
    return jsonify(id=u["id"], name=u["name"], email=u["email"], role=u["role"],
                   verificationStatus=u["verificationStatus"], token=make_token(u))


# =====================================================================
# Jobs
# =====================================================================
def job_dto(j):
    emp = user_by_id(j["employerId"])
    apps = [a for a in DB["apps"] if a["jobId"] == j["id"]]
    return {"id": j["id"], "title": j["title"], "category": j["category"],
            "location": j["location"], "district": j["district"],
            "description": j["description"], "requiredSkills": j["requiredSkills"],
            "pay": money(j["pay"]), "per": j["per"], "urgent": j["urgent"],
            "status": j["status"], "workersNeeded": j["workersNeeded"],
            "expectedUnits": j["expectedUnits"], "startDate": j["startDate"],
            "endDate": j["endDate"], "employerId": j["employerId"],
            "employerName": emp["name"] if emp else "",
            "employerVerified": bool(emp and emp["verificationStatus"] == "verified"),
            "applications": len(apps),
            "positionsFilled": sum(1 for a in apps if a["status"] in ("accepted", "completed")),
            "createdAt": j["createdAt"]}


@app.get("/api/jobs")
def jobs():
    q = request.args
    try:
        min_pay = float(q.get("minPay")) if q.get("minPay") else None
        max_pay = float(q.get("maxPay")) if q.get("maxPay") else None
    except ValueError:
        return jsonify(message="Invalid wage filter."), 400
    if min_pay is not None and min_pay < 0:
        return jsonify(message="Minimum wage cannot be negative."), 400
    if min_pay is not None and max_pay is not None and min_pay > max_pay:
        return jsonify(message="The minimum wage cannot be higher than the maximum."), 400

    search = (q.get("search") or "").lower()
    cat = q.get("category") or ""
    loc = (q.get("location") or "").lower()
    dist = (q.get("district") or "").lower()
    skills = [x.strip().lower() for x in (q.get("skills") or "").split(",") if len(x.strip()) > 1]
    urgent_only = q.get("urgentOnly") in ("true", "True", "1")
    available_only = q.get("availableOnly") in ("true", "True", "1")
    verified_only = q.get("verifiedOnly") in ("true", "True", "1")
    sort = q.get("sort") or "relevance"
    page = max(1, int(q.get("page") or 1))
    size = int(q.get("pageSize") or 20)
    if size < 1 or size > 100:
        size = 20

    out = []
    for j in DB["jobs"]:
        if j["status"] != "open":
            continue
        emp = user_by_id(j["employerId"])
        hay = " ".join([j["title"], j["category"], j["description"], j["requiredSkills"],
                        emp["name"] if emp else ""]).lower()
        if search and search not in hay:
            continue
        if cat and j["category"] != cat:
            continue
        if loc and loc not in j["location"].lower():
            continue
        if dist and j["district"].lower() != dist:
            continue
        if min_pay is not None and j["pay"] < min_pay:
            continue
        if max_pay is not None and j["pay"] > max_pay:
            continue
        if urgent_only and not j["urgent"]:
            continue
        if verified_only and not (emp and emp["verificationStatus"] == "verified"):
            continue
        if skills:
            blob = (j["requiredSkills"] + " " + j["title"] + " " + j["category"]).lower()
            if not all(sk in blob for sk in skills):
                continue
        if available_only:
            hired = sum(1 for a in DB["apps"]
                        if a["jobId"] == j["id"] and a["status"] in ("accepted", "completed"))
            if hired >= j["workersNeeded"]:
                continue
        out.append(j)

    if sort == "newest":
        out.sort(key=lambda j: -j["id"])
    elif sort == "wage_high":
        out.sort(key=lambda j: (-j["pay"], -j["id"]))
    elif sort == "wage_low":
        out.sort(key=lambda j: (j["pay"], -j["id"]))
    else:
        out.sort(key=lambda j: (not j["urgent"], -j["id"]))

    total = len(out)
    sl = out[(page - 1) * size: page * size]
    return jsonify(total=total, page=page, pageSize=size,
                   totalPages=(total + size - 1) // size, sort=sort,
                   jobs=[job_dto(j) for j in sl])


@app.get("/api/jobs/<int:jid>")
def job_details(jid):
    j = next((x for x in DB["jobs"] if x["id"] == jid), None)
    if not j:
        return jsonify(message="Job not found."), 404
    emp = user_by_id(j["employerId"]) or {}
    stars = [r["stars"] for r in DB["ratings"] if r["subjectId"] == j["employerId"]]
    u = current_user()
    applied = bool(u and any(a["jobId"] == jid and a["workerId"] == u["id"] for a in DB["apps"]))
    return jsonify(job=job_dto(j), alreadyApplied=applied, employer={
        "id": j["employerId"], "name": emp.get("name", ""),
        "verified": emp.get("verificationStatus") == "verified",
        "organizationName": emp.get("organizationName", ""),
        "location": emp.get("location", ""), "memberSince": emp.get("createdAt"),
        "jobsPosted": sum(1 for x in DB["jobs"] if x["employerId"] == j["employerId"]),
        "rating": round(sum(stars) / len(stars), 1) if stars else 0,
        "ratingCount": len(stars)})


def validate_job(d):
    if len((d.get("title") or "").strip()) < 3:
        return "Please enter a job title of at least 3 characters."
    if not (d.get("category") or "").strip():
        return "Please choose a category."
    if not (d.get("location") or "").strip():
        return "Please enter where the work is."
    if not d.get("pay") or float(d["pay"]) <= 0:
        return "Please enter the wage amount."
    if float(d["pay"]) > 1000000:
        return "That wage looks too high. Please check the amount."
    if d.get("per") and d["per"] not in ("day", "shift", "hour"):
        return "Pay unit must be day, shift or hour."
    w = int(d.get("workersNeeded") or 1)
    if w < 1 or w > 500:
        return "Number of workers must be between 1 and 500."
    return None



def resolve_project(pid, u):
    """A posting is only filed under a project the caller actually owns."""
    if not pid:
        return None
    pr = next((x for x in DB["projects"] if x["id"] == int(pid)), None)
    return pr["id"] if pr and pr["organizationId"] == u["id"] else None


@app.post("/api/jobs")
def post_job():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    problem = validate_job(d)
    if problem:
        return jsonify(message=problem), 400
    j = {"id": nid("job"), "title": d["title"].strip(), "category": d["category"].strip(),
         "location": d["location"].strip(),
         "district": (d.get("district") or d["location"]).strip(),
         "description": (d.get("description") or "").strip(),
         "requiredSkills": (d.get("requiredSkills") or "").strip(),
         "pay": money(d["pay"]), "per": d.get("per") or "day",
         "urgent": bool(d.get("urgent")), "status": "open",
         "workersNeeded": int(d.get("workersNeeded") or 1),
         "expectedUnits": int(d.get("expectedUnits") or 1),
         "startDate": d.get("startDate"), "endDate": d.get("endDate"),
         "employerId": u["id"], "projectId": resolve_project(d.get("projectId"), u),
         "createdAt": now(), "updatedAt": None}
    DB["jobs"].append(j)

    # notify matching workers
    matched = []
    for w in DB["users"]:
        if w["role"] != "worker" or not w.get("available", True) or not w.get("isActive", True):
            continue
        score = 0
        have = [x.strip().lower() for x in (w["skills"] or "").split(",") if x.strip()]
        req = [x.strip().lower() for x in (j["requiredSkills"] or "").split(",") if x.strip()]
        if req and have:
            m = sum(1 for r in req if any(h[:4] in r or r[:4] in h for h in have))
            if m:
                score += int(40 * m / len(req))
        if any(h[:4] in j["category"].lower() for h in have):
            score += 15
        if w.get("district", "").lower() == j["district"].lower():
            score += 20
        if score >= 30:
            matched.append(w)
            note(w["id"], "job_match", "New job that matches your profile",
                 f'"{j["title"]}" in {j["location"]} pays Rs. {j["pay"]:,.0f} per {j["per"]}.')
    mail_job_posted(j, matched[:25])
    return jsonify(id=j["id"], message="Job posted."), 201


@app.put("/api/jobs/<int:jid>")
def update_job(jid):
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    j = next((x for x in DB["jobs"] if x["id"] == jid), None)
    if not j:
        return jsonify(message="Job not found."), 404
    if j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    if j["status"] == "closed":
        return jsonify(message="A closed job cannot be edited."), 400
    d = request.get_json(force=True)
    problem = validate_job(d)
    if problem:
        return jsonify(message=problem), 400
    hired = sum(1 for a in DB["apps"] if a["jobId"] == jid and a["status"] in ("accepted", "completed"))
    # The raw value is compared, exactly as the C# does: asking for 0 workers
    # when one is already hired is a reduction and must be refused.
    if int(d.get("workersNeeded") or 0) < hired:
        return jsonify(message=f"You have already hired {hired} worker(s), so the number required cannot be lower than that."), 400
    if hired > 0 and money(d["pay"]) != money(j["pay"]):
        return jsonify(message="The wage cannot be changed after a worker has been hired for this job."), 400
    j.update({"title": d["title"].strip(), "category": d["category"].strip(),
              "location": d["location"].strip(),
              "district": (d.get("district") or d["location"]).strip(),
              "description": (d.get("description") or "").strip(),
              "requiredSkills": (d.get("requiredSkills") or "").strip(),
              "pay": money(d["pay"]), "urgent": bool(d.get("urgent")),
              "workersNeeded": int(d.get("workersNeeded") or 1),
              "expectedUnits": int(d.get("expectedUnits") or j.get("expectedUnits") or 1),
              "startDate": d.get("startDate"), "endDate": d.get("endDate"),
              "projectId": resolve_project(d.get("projectId"), u),
              "updatedAt": now()})
    return jsonify(message="Job updated.")


@app.delete("/api/jobs/<int:jid>")
def close_job(jid):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    j = next((x for x in DB["jobs"] if x["id"] == jid), None)
    if not j:
        return jsonify(message="Job not found."), 404
    if j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    if j["status"] == "closed":
        return jsonify(message="This job is already closed."), 400
    j["status"] = "closed"
    return jsonify(message="Job closed.")


# =====================================================================
# Applications
# =====================================================================
ALLOWED_NEXT = {"pending": ["shortlisted", "accepted", "rejected"],
                "shortlisted": ["accepted", "rejected"],
                "accepted": ["completed", "rejected"],
                "completed": [], "rejected": []}


@app.post("/api/applications")
def apply_job():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    if u["role"] != "worker":
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    j = next((x for x in DB["jobs"] if x["id"] == d.get("jobId")), None)
    if not j:
        return jsonify(message="Job not found."), 404
    if j["status"] != "open":
        return jsonify(message="This job is no longer accepting applications."), 400
    if j["employerId"] == u["id"]:
        return jsonify(message="You cannot apply to your own job posting."), 400
    ex = next((a for a in DB["apps"] if a["jobId"] == j["id"] and a["workerId"] == u["id"]), None)
    if ex:
        if ex["status"] in ("accepted", "completed"):
            return jsonify(message="You are already assigned to this job."), 409
        return jsonify(message="You have already applied for this job."), 409
    hired = sum(1 for a in DB["apps"] if a["jobId"] == j["id"] and a["status"] in ("accepted", "completed"))
    if hired >= j["workersNeeded"]:
        return jsonify(message="This job has already hired all the workers it needs."), 400

    DB["apps"].append({"id": nid("app"), "jobId": j["id"], "workerId": u["id"],
                       "status": "pending", "message": (d.get("message") or "").strip(),
                       "createdAt": now(), "shortlistedAt": None, "acceptedAt": None,
                       "rejectedAt": None, "completedAt": None})
    note(j["employerId"], "application", "New applicant", f'{u["name"]} applied for "{j["title"]}".')
    mail_application(u, j)
    return jsonify(message="Application submitted.")


@app.get("/api/applications/mine")
def my_apps():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    out = []
    for a in sorted([a for a in DB["apps"] if a["workerId"] == u["id"]], key=lambda a: -a["id"]):
        j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
        emp = user_by_id(j["employerId"]) or {}
        out.append({"id": a["id"], "jobId": a["jobId"], "jobTitle": j["title"],
                    "employerName": emp.get("name", ""), "location": j["location"],
                    "pay": money(j["pay"]), "per": j["per"], "status": a["status"],
                    "createdAt": a["createdAt"], "acceptedAt": a["acceptedAt"],
                    "completedAt": a["completedAt"]})
    return jsonify(out)


@app.put("/api/applications/<int:aid>/status")
def app_status(aid):
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    target = (d.get("status") or "").strip().lower()
    if target not in ("pending", "shortlisted", "accepted", "rejected", "completed"):
        return jsonify(message="Invalid status."), 400
    a = next((x for x in DB["apps"] if x["id"] == aid), None)
    if not a:
        return jsonify(message="Application not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
    if j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    if a["status"] == target:
        return jsonify(message=f"This application is already {target}."), 400
    if target not in ALLOWED_NEXT.get(a["status"], []):
        if a["status"] == "completed":
            msg = "Completed work cannot be changed."
        elif a["status"] == "rejected":
            msg = "A rejected application cannot be changed."
        elif target == "completed":
            msg = "A worker must be hired before their work can be verified as completed."
        else:
            msg = f'An application cannot move from {a["status"]} to {target}.'
        return jsonify(message=msg), 400

    if target == "accepted":
        hired = sum(1 for x in DB["apps"]
                    if x["jobId"] == a["jobId"] and x["status"] in ("accepted", "completed"))
        if hired >= j["workersNeeded"]:
            return jsonify(message="This job has already hired all the workers it needs."), 400

    prev = a["status"]
    a["status"] = target
    stamp = now()
    a[{"shortlisted": "shortlistedAt", "accepted": "acceptedAt",
       "rejected": "rejectedAt", "completed": "completedAt"}.get(target, "createdAt")] = stamp

    if target == "completed":
        # Only approved days count towards what is owed.
        recs = [w for w in DB["work"] if w["applicationId"] == a["id"]
                and w.get("status", "approved") == "approved"]
        units = sum(w["units"] for w in recs) if recs else 1
        total = money(j["pay"] * units)
        if not any(p["applicationId"] == a["id"] for p in DB["payments"]):
            pay = {"id": nid("payment"), "jobId": a["jobId"], "workerId": a["workerId"],
                   "applicationId": a["id"], "agreedRate": money(j["pay"]),
                   "rateUnit": j["per"], "unitsWorked": units, "amount": total,
                   "amountPaid": 0, "status": "pending", "paidAt": None, "method": "",
                   "notes": "", "workerConfirmed": False, "confirmedAmount": 0, "workerConfirmedAt": None,
                   "workerDisputeNote": "", "createdAt": now()}
            DB["payments"].append(pay)
            DB["audits"].append({"id": nid("audit"), "paymentId": pay["id"], "action": "created",
                                 "fromStatus": "", "toStatus": "pending", "amountAtChange": total,
                                 "actorUserId": u["id"], "actorRole": u["role"],
                                 "note": f'Raised automatically when work on "{j["title"]}" was verified.',
                                 "createdAt": now()})

    headline = {"shortlisted": "You have been shortlisted", "accepted": "You have been hired",
                "rejected": "Application not successful", "completed": "Work verified"}.get(target, "Application updated")
    detail = {"shortlisted": f'Your application for "{j["title"]}" has been shortlisted.',
              "accepted": f'You were selected for "{j["title"]}". The employer will contact you.',
              "rejected": f'Your application for "{j["title"]}" was not successful this time.',
              "completed": f'Your work on "{j["title"]}" was verified and your payment record has been raised.'}.get(target, "")
    note(a["workerId"], target, headline, detail)
    mail_status(a, j, target)
    return jsonify(message="Status updated.", **{"from": prev, "to": target})


@app.post("/api/applications/<int:aid>/work")
def add_work(aid):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    a = next((x for x in DB["apps"] if x["id"] == aid), None)
    if not a:
        return jsonify(message="Application not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])

    is_employer = j["employerId"] == u["id"] or u["role"] == "admin"
    is_worker = a["workerId"] == u["id"]
    if not is_employer and not is_worker:
        return jsonify(message="Forbidden"), 403

    if a["status"] not in ("accepted", "completed"):
        return jsonify(message="Work can only be recorded for a worker who has been hired."), 400

    settled = None
    if a["status"] == "completed":
        settled = next((x for x in DB["payments"] if x.get("applicationId") == aid), None)
        if settled and settled["amountPaid"] > 0:
            return jsonify(message="Payment for this job has already started, so the work record "
                                   "cannot be changed. Ask the employer to record a separate payment "
                                   "for any extra work, or raise a dispute on the existing payment."), 400

    d = request.get_json(force=True)
    units = float(d.get("units") or 1)
    if units <= 0 or units > 24:
        return jsonify(message="Units worked must be between 0 and 24."), 400
    wd = (d.get("workDate") or datetime.date.today().isoformat())[:10]
    if any(w["applicationId"] == aid and w["workDate"][:10] == wd for w in DB["work"]):
        return jsonify(message="Work has already been recorded for that date."), 409

    approved = is_employer
    DB["work"].append({"id": nid("work"), "jobId": a["jobId"], "workerId": a["workerId"],
                       "applicationId": aid, "workDate": wd, "units": units,
                       "unit": j["per"], "rateApplied": money(j["pay"]),
                       "lineTotal": money(j["pay"] * units),
                       "notes": (d.get("notes") or "").strip(),
                       "status": "approved" if approved else "pending",
                       "submittedByUserId": u["id"], "decisionNote": "",
                       "verified": approved,
                       "verifiedAt": now() if approved else None, "createdAt": now()})

    if not approved:
        note(j["employerId"], "work", "Work day submitted for approval",
             f'{u["name"]} submitted {units:g} {j["per"]}(s) on {wd} for "{j["title"]}". '
             "Approve it to include it in their payment.")
        return jsonify(message="Submitted. The employer will review it and add it to your "
                               "payment once approved.", status="pending")

    if settled:
        total = recalculate_payment(settled, aid, u)
        return jsonify(message=f"Work recorded, and the payment was updated to {total:.2f}.",
                       status="approved", amount=total)

    return jsonify(message="Work recorded.", status="approved")


def recalculate_payment(p, aid, actor):
    """Re-derive a payment from the approved work behind it."""
    units = sum(w["units"] for w in DB["work"]
                if w["applicationId"] == aid and w.get("status", "approved") == "approved") or 1
    previous = p["amount"]
    rate = p["agreedRate"] or 0
    total = money(rate * units)
    if total == previous:
        return total
    p["unitsWorked"] = units
    p["amount"] = total
    DB["audits"].append({"id": nid("audit"), "paymentId": p["id"], "action": "recalculated",
                         "fromStatus": p["status"], "toStatus": p["status"],
                         "amountAtChange": total, "actorUserId": actor["id"],
                         "actorRole": actor["role"],
                         "note": f"Work record changed after completion: amount updated from "
                                 f"{previous:.2f} to {total:.2f}.", "createdAt": now()})
    note(p["workerId"], "payment", "Payment amount updated",
         f"The amount owed changed from Rs. {previous:,.2f} to Rs. {total:,.2f} "
         "after the work record was updated.")
    return total


@app.put("/api/applications/work/<int:rid>")
def decide_work(rid):
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    w = next((x for x in DB["work"] if x["id"] == rid), None)
    if not w:
        return jsonify(message="Work record not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == w["jobId"])
    if j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    if w.get("status", "approved") != "pending":
        return jsonify(message="That work record has already been decided."), 400

    d = request.get_json(force=True, silent=True) or {}
    approve = bool(d.get("approve"))
    aid = w["applicationId"]
    p = next((x for x in DB["payments"] if x.get("applicationId") == aid), None)

    if approve and p and p["amountPaid"] > 0:
        return jsonify(message="Payment for this job has already started, so extra work cannot "
                               "be added to it. Record a separate payment for the additional work."), 400

    w["status"] = "approved" if approve else "rejected"
    w["verified"] = approve
    w["verifiedAt"] = now() if approve else None
    w["decisionNote"] = (d.get("note") or "").strip()

    total = recalculate_payment(p, aid, u) if (approve and p) else None

    note(w["workerId"], "work",
         "Work day approved" if approve else "Work day not approved",
         f'Your {w["units"]:g} {w["unit"]}(s) on {w["workDate"]} for "{j["title"]}" '
         + ("was approved." if approve else "was not approved."))

    return jsonify(message="Work approved." if approve else "Work rejected.",
                   status=w["status"], amount=total)


@app.get("/api/applications/<int:aid>/work")
def get_work(aid):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    a = next((x for x in DB["apps"] if x["id"] == aid), None)
    if not a:
        return jsonify(message="Application not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
    if a["workerId"] != u["id"] and j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    recs = [w for w in DB["work"] if w["applicationId"] == aid]
    appr = [w for w in recs if w.get("status", "approved") == "approved"]
    pend = [w for w in recs if w.get("status", "approved") == "pending"]
    return jsonify(applicationId=aid, jobTitle=j["title"], rate=money(j["pay"]), unit=j["per"],
                   totalUnits=sum(w["units"] for w in appr),
                   totalEarned=money(sum(w["lineTotal"] for w in appr)),
                   pendingUnits=sum(w["units"] for w in pend), pendingCount=len(pend),
                   records=[{"id": w["id"], "workDate": w["workDate"], "units": w["units"],
                             "unit": w["unit"], "rateApplied": w["rateApplied"],
                             "lineTotal": w["lineTotal"], "notes": w["notes"],
                             "verified": w["verified"],
                             "status": w.get("status", "approved"),
                             "decisionNote": w.get("decisionNote", ""),
                             "submittedByWorker": w.get("submittedByUserId") == w["workerId"]}
                            for w in recs])


# =====================================================================
# Payments
# =====================================================================
def payment_dto(p, for_worker=True):
    j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
    emp = user_by_id(j["employerId"]) or {}
    w = user_by_id(p["workerId"]) or {}
    base = {"id": p["id"], "jobId": p["jobId"], "jobTitle": j["title"],
            "agreedRate": money(p["agreedRate"]), "rateUnit": p["rateUnit"],
            "unitsWorked": p["unitsWorked"], "amount": money(p["amount"]),
            "amountPaid": money(p["amountPaid"]),
            "outstanding": money(p["amount"] - p["amountPaid"]),
            "status": p["status"], "method": p["method"], "notes": p["notes"],
            "workerConfirmed": p["workerConfirmed"],
            "confirmedAmount": money(p.get("confirmedAmount", 0)),
            "awaitingConfirmation": money(p["amountPaid"] - p.get("confirmedAmount", 0)),
            "workerConfirmedAt": p["workerConfirmedAt"],
            "paidAt": p["paidAt"], "createdAt": p["createdAt"]}
    if for_worker:
        base["employerName"] = emp.get("name", "")
    else:
        base["workerName"] = w.get("name", "")
        base["workerId"] = p["workerId"]
    return base


@app.get("/api/payments/mine")
def my_payments():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    rows = sorted([p for p in DB["payments"] if p["workerId"] == u["id"]], key=lambda p: -p["id"])
    return jsonify([payment_dto(p) for p in rows])


@app.put("/api/payments/<int:pid>/pay")
def record_payment(pid):
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    p = next((x for x in DB["payments"] if x["id"] == pid), None)
    if not p:
        return jsonify(message="Payment not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
    if j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    if p["status"] == "paid":
        return jsonify(message="This payment has already been settled in full and cannot be changed."), 400

    outstanding = money(p["amount"] - p["amountPaid"])
    if outstanding <= 0:
        return jsonify(message="There is nothing outstanding on this payment."), 400

    d = request.get_json(force=True, silent=True) or {}
    amount = money(d["amount"]) if d.get("amount") else outstanding
    if amount <= 0:
        return jsonify(message="The payment amount must be greater than zero."), 400
    if amount > outstanding:
        return jsonify(message=f"That is more than the outstanding balance of {outstanding:.2f}."), 400

    frm = p["status"]
    p["amountPaid"] = money(p["amountPaid"] + amount)
    p["method"] = (d.get("method") or p["method"] or "").strip()
    if d.get("notes"):
        p["notes"] = d["notes"].strip()
    settled = p["amountPaid"] >= p["amount"]
    p["status"] = "paid" if settled else "partial"
    if settled and not p["paidAt"]:
        p["paidAt"] = now()

    # New money the worker has not acknowledged re-opens confirmation.
    if p["amountPaid"] > p.get("confirmedAmount", 0):
        p["workerConfirmed"] = False

    DB["audits"].append({"id": nid("audit"), "paymentId": p["id"], "action": "recorded",
                         "fromStatus": frm, "toStatus": p["status"], "amountAtChange": amount,
                         "actorUserId": u["id"], "actorRole": u["role"],
                         "note": "Employer recorded payment.", "createdAt": now()})
    note(p["workerId"], "payment",
         "Payment recorded in full" if settled else "Part payment recorded",
         f'Rs. {amount:,.2f} for "{j["title"]}" was recorded.')
    return jsonify(message="Payment recorded in full." if settled else "Part payment recorded.",
                   status=p["status"], amountPaid=p["amountPaid"],
                   outstanding=money(p["amount"] - p["amountPaid"]),
                   workerConfirmed=p["workerConfirmed"],
                   awaitingConfirmation=money(p["amountPaid"] - p.get("confirmedAmount", 0)))


@app.put("/api/payments/<int:pid>/confirm")
def confirm_payment(pid):
    u = current_user()
    if not u or u["role"] != "worker":
        return jsonify(message="Forbidden"), 403
    p = next((x for x in DB["payments"] if x["id"] == pid), None)
    if not p:
        return jsonify(message="Payment not found."), 404
    if p["workerId"] != u["id"]:
        return jsonify(message="Forbidden"), 403
    if p["amountPaid"] <= 0:
        return jsonify(message="The employer has not recorded any payment yet."), 400
    newly = money(p["amountPaid"] - p.get("confirmedAmount", 0))
    if newly <= 0:
        out = money(p["amount"] - p["amountPaid"])
        return jsonify(message="You have already confirmed everything recorded as paid so far."
                               + (f" Rs. {out:,.2f} of this job is still unpaid." if out > 0 else "")), 400

    before = p.get("confirmedAmount", 0)
    p["confirmedAmount"] = p["amountPaid"]
    p["workerConfirmed"] = True
    p["workerConfirmedAt"] = now()
    fully = p["status"] == "paid"

    DB["audits"].append({"id": nid("audit"), "paymentId": p["id"], "action": "confirmed",
                         "fromStatus": p["status"], "toStatus": p["status"],
                         "amountAtChange": newly, "actorUserId": u["id"],
                         "actorRole": u["role"],
                         "note": (f"Worker confirmed a further {newly:.2f} "
                                  f"(total confirmed {p['confirmedAmount']:.2f} of {p['amount']:.2f})."
                                  if before > 0 else
                                  f"Worker confirmed receipt of {newly:.2f} of {p['amount']:.2f}."),
                         "createdAt": now()})
    j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
    note(j["employerId"], "payment", "Payment confirmed by worker",
         f'The worker confirmed receiving the full amount for "{j["title"]}".' if fully else
         f'The worker confirmed receiving Rs. {p["confirmedAmount"]:,.2f} for "{j["title"]}".')
    return jsonify(message=("Thank you, the full payment has been confirmed." if fully else
                            f"Thank you. You have confirmed Rs. {p['confirmedAmount']:,.2f} of "
                            f"Rs. {p['amount']:,.2f}. You will be asked to confirm again when the "
                            "employer pays the balance."),
                   confirmedAmount=p["confirmedAmount"],
                   outstanding=money(p["amount"] - p["amountPaid"]),
                   fullyConfirmed=fully)


@app.put("/api/payments/<int:pid>/dispute")
def dispute_payment(pid):
    u = current_user()
    if not u or u["role"] != "worker":
        return jsonify(message="Forbidden"), 403
    p = next((x for x in DB["payments"] if x["id"] == pid), None)
    if not p:
        return jsonify(message="Payment not found."), 404
    if p["workerId"] != u["id"]:
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    n = (d.get("note") or "").strip()
    if len(n) < 5:
        return jsonify(message="Please explain the problem in a few words."), 400
    p["workerConfirmed"] = False
    p["workerDisputeNote"] = n
    DB["audits"].append({"id": nid("audit"), "paymentId": p["id"], "action": "disputed",
                         "fromStatus": p["status"], "toStatus": p["status"],
                         "amountAtChange": p["amountPaid"], "actorUserId": u["id"],
                         "actorRole": u["role"], "note": n, "createdAt": now()})
    return jsonify(message="Your dispute has been recorded and the employer notified.")


@app.get("/api/payments/<int:pid>/audit")
def payment_audit(pid):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    p = next((x for x in DB["payments"] if x["id"] == pid), None)
    if not p:
        return jsonify(message="Payment not found."), 404
    j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
    if p["workerId"] != u["id"] and j["employerId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    return jsonify([a for a in DB["audits"] if a["paymentId"] == pid])


# =====================================================================
# Ratings
# =====================================================================
@app.get("/api/ratings/user/<int:uid>")
def ratings_for(uid):
    out = []
    for r in sorted([r for r in DB["ratings"] if r["subjectId"] == uid], key=lambda r: -r["id"]):
        j = next((x for x in DB["jobs"] if x["id"] == r["jobId"]), None)
        out.append({"id": r["id"], "jobId": r["jobId"], "jobTitle": j["title"] if j else "",
                    "authorName": (user_by_id(r["authorId"]) or {}).get("name", ""),
                    "subjectName": (user_by_id(r["subjectId"]) or {}).get("name", ""),
                    "stars": r["stars"], "comment": r["comment"], "createdAt": r["createdAt"]})
    return jsonify(out)


@app.get("/api/ratings/mine")
def ratings_mine():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    return ratings_for(u["id"])


@app.get("/api/ratings/pending")
def ratings_pending():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    me = u["id"]
    pend = []
    for a in DB["apps"]:
        if a["status"] != "completed":
            continue
        j = next((x for x in DB["jobs"] if x["id"] == a["jobId"]), None)
        if not j:
            continue
        if a["workerId"] == me:
            pend.append({"jobId": j["id"], "jobTitle": j["title"], "subjectId": j["employerId"],
                         "subjectName": (user_by_id(j["employerId"]) or {}).get("name", ""),
                         "subjectRole": "employer"})
        if j["employerId"] == me:
            pend.append({"jobId": j["id"], "jobTitle": j["title"], "subjectId": a["workerId"],
                         "subjectName": (user_by_id(a["workerId"]) or {}).get("name", ""),
                         "subjectRole": "worker"})
    done = {(r["jobId"], r["subjectId"]) for r in DB["ratings"] if r["authorId"] == me}
    return jsonify([p for p in pend if (p["jobId"], p["subjectId"]) not in done])


@app.post("/api/ratings")
def create_rating():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    d = request.get_json(force=True)
    me = u["id"]
    stars = int(d.get("stars") or 0)
    if stars < 1 or stars > 5:
        return jsonify(message="Please give a rating between 1 and 5 stars."), 400
    if d.get("subjectId") == me:
        return jsonify(message="You cannot rate yourself."), 400
    j = next((x for x in DB["jobs"] if x["id"] == d.get("jobId")), None)
    if not j:
        return jsonify(message="Job not found."), 404
    subject = user_by_id(d.get("subjectId"))
    if not subject:
        return jsonify(message="The person you are reviewing was not found."), 404

    if j["employerId"] == me:
        ok = any(a["jobId"] == j["id"] and a["workerId"] == d["subjectId"] and a["status"] == "completed"
                 for a in DB["apps"])
        if not ok:
            return jsonify(message="You can only review a worker who completed this job for you."), 400
        role = "worker"
    else:
        mine = any(a["jobId"] == j["id"] and a["workerId"] == me and a["status"] == "completed"
                   for a in DB["apps"])
        if not mine:
            return jsonify(message="You can only review someone after you have completed their job."), 400
        if d["subjectId"] != j["employerId"]:
            return jsonify(message="You can only review the employer who hired you for this job."), 400
        role = "employer"

    if any(r["jobId"] == j["id"] and r["authorId"] == me and r["subjectId"] == d["subjectId"]
           for r in DB["ratings"]):
        return jsonify(message="You have already reviewed this job."), 409

    DB["ratings"].append({"id": nid("rating"), "jobId": j["id"], "authorId": me,
                          "subjectId": d["subjectId"], "stars": stars,
                          "comment": (d.get("comment") or "").strip(),
                          "subjectRole": role, "createdAt": now()})
    note(d["subjectId"], "rating", "New review received",
         f'{u["name"]} rated you {stars} star(s) for "{j["title"]}".')
    return jsonify(message="Thank you, your review has been saved.")


# =====================================================================
# Recommendations
# =====================================================================
SYN = {"mason": ["masonry", "brick", "construction", "build"],
       "construction": ["mason", "masonry", "build", "site", "labour"],
       "paint": ["painting", "painter", "decorat"],
       "clean": ["cleaning", "cleaner", "housekeep"],
       "driv": ["driving", "driver", "transport", "deliver"],
       "deliver": ["delivery", "driv", "transport"],
       "farm": ["farming", "agriculture", "harvest"],
       "agricultur": ["farm", "harvest", "estate"],
       "load": ["loading", "warehous", "packing"],
       "warehous": ["load", "storage", "manufactur"]}


def norm(s):
    c = re.sub(r"[^a-z0-9 ]", "", s.strip().lower()).strip()
    for suf in ("ing", "er", "ers", "s"):
        if len(c) > 4 and c.endswith(suf):
            return c[:-len(suf)]
    return c


def align(a, b):
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) >= 4 and len(y) >= 4 and (x in y or y in x):
        return True
    return y in SYN.get(x, [])


def split_skills(raw):
    return [s.strip() for s in re.split(r"[,;/|]", raw or "") if len(s.strip()) > 1]


@app.get("/api/recommendations")
def recommendations():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    if u["role"] != "worker":
        # Matches [Authorize(Roles = "worker")] on RecommendationsController.
        return jsonify(message="Forbidden"), 403

    take = int(request.args.get("take") or 10)
    applied = {a["jobId"] for a in DB["apps"] if a["workerId"] == u["id"]}
    have = split_skills(u["skills"])
    rates = [p["agreedRate"] for p in DB["payments"] if p["workerId"] == u["id"]]
    typical = sum(rates) / len(rates) if rates else 0

    scored = []
    for j in DB["jobs"]:
        if j["status"] != "open" or j["employerId"] == u["id"] or j["id"] in applied:
            continue
        hired = sum(1 for a in DB["apps"] if a["jobId"] == j["id"] and a["status"] in ("accepted", "completed"))
        if hired >= j["workersNeeded"]:
            continue

        reasons, score = [], 0
        req = split_skills(j["requiredSkills"])
        if req and have:
            matched = [r for r in req if any(align(h, r) for h in have)]
            if matched:
                score += round(40 * len(matched) / len(req))
                reasons.append("You have all the skills asked for (" + ", ".join(matched) + ")"
                               if len(matched) == len(req)
                               else "Matches your skills: " + ", ".join(matched))
        elif have and not req:
            score += 10

        if j["category"] and any(align(h, j["category"]) for h in have):
            score += 15
            reasons.append(f'You work in {j["category"]}')

        same_town = u.get("location", "") and u["location"].lower() == j["location"].lower()
        same_dist = u.get("district", "") and u["district"].lower() == j["district"].lower()
        if same_town:
            score += 30
            reasons.append(f'In your area ({j["location"]})')
        elif same_dist:
            score += 20
            reasons.append(f'In your district ({j["district"]})')

        if u.get("experienceYears", 0) >= 3 and req and any(align(h, r) for h in have for r in req):
            score += 10
            reasons.append(f'{u["experienceYears"]} years of relevant experience')

        if typical > 0 and j["pay"] >= typical:
            score += 10
            reasons.append("Pays more than your usual rate" if j["pay"] > typical else "Matches your usual rate")
        elif typical == 0 and j["pay"] > 0:
            score += 5

        if j["urgent"]:
            score += 5
            reasons.append("Employer needs someone urgently")
        score += 5  # freshness; all seeded jobs are new

        emp = user_by_id(j["employerId"])
        if emp and emp["verificationStatus"] == "verified":
            reasons.append("Verified employer")

        if score <= 0 or not reasons:
            continue
        maxp = 40 + 15 + 20 + 10 + 10 + 10 + 5 + 5
        d = job_dto(j)
        d["matchScore"] = min(100, round(score * 100 / maxp))
        d["reasons"] = reasons
        scored.append(d)

    scored.sort(key=lambda x: (-x["matchScore"], -x["id"]))
    bare = not u.get("skills") and not u.get("district") and not u.get("location")
    return jsonify(recommendations=scored[:take], profileComplete=not bare,
                   message=("Add your skills and district to your profile to get job recommendations that suit you."
                            if bare else None if scored else
                            "No matching jobs right now."))


# =====================================================================
# Profile / organization / categories / contact / notifications
# =====================================================================
@app.get("/api/profile")
def get_profile():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    return jsonify(build_profile(u["id"], True))


@app.get("/api/profile/<int:uid>")
def get_profile_by_id(uid):
    viewer = current_user()
    owner = bool(viewer and viewer["id"] == uid)
    admin = bool(viewer and viewer["role"] == "admin")
    dealings = bool(viewer and any(
        a["workerId"] == uid and next(x for x in DB["jobs"] if x["id"] == a["jobId"])["employerId"] == viewer["id"]
        for a in DB["apps"]))
    p = build_profile(uid, owner or admin or dealings)
    if not p:
        return jsonify(message="User not found."), 404
    return jsonify(p)


def build_profile(uid, owner):
    u = user_by_id(uid)
    if not u:
        return None
    stars = [r["stars"] for r in DB["ratings"] if r["subjectId"] == uid]
    earned = sum(p["amountPaid"] for p in DB["payments"] if p["workerId"] == uid)
    completed = sum(1 for a in DB["apps"] if a["workerId"] == uid and a["status"] == "completed")
    hist = []
    for a in [a for a in DB["apps"] if a["workerId"] == uid and a["status"] == "completed"][:10]:
        j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
        hist.append({"jobId": j["id"], "jobTitle": j["title"], "category": j["category"],
                     "location": j["location"],
                     "employerName": (user_by_id(j["employerId"]) or {}).get("name", ""),
                     "completedAt": a["completedAt"]})
    return {"id": u["id"], "name": u["name"], "email": u["email"] if owner else "",
            "phone": u["phone"] if owner else "", "role": u["role"], "skills": u["skills"],
            "location": u["location"], "district": u["district"], "bio": u["bio"],
            "experience": u["experience"], "experienceYears": u["experienceYears"],
            "certifications": u["certifications"], "available": u["available"],
            "verificationStatus": u["verificationStatus"],
            "isVerified": u["verificationStatus"] == "verified",
            "createdAt": u["createdAt"],
            "averageRating": round(sum(stars) / len(stars), 1) if stars else 0,
            "ratingCount": len(stars), "jobsCompleted": completed,
            "totalEarned": money(earned) if owner else 0,
            # Only the CV's details, and only for someone allowed to download it.
            "hasCv": bool(owner and uid in DB["cvs"]),
            "cvFileName": DB["cvs"][uid]["fileName"] if owner and uid in DB["cvs"] else "",
            "cvSizeBytes": len(DB["cvs"][uid]["data"]) if owner and uid in DB["cvs"] else 0,
            "cvUploadedAt": DB["cvs"][uid]["uploadedAt"] if owner and uid in DB["cvs"] else None,
            "workHistory": hist}


# =====================================================================
# CV upload / download / removal (mirrors ProfileController's CV actions)
# =====================================================================
@app.post("/api/profile/cv")
def upload_cv():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    if u["role"] != "worker":
        return jsonify(message="Forbidden"), 403
    # [RequestSizeLimit]: an oversized request is refused before it is read.
    if (request.content_length or 0) > CV_MAX_REQUEST:
        return Response("", status=413)

    f = request.files.get("file")
    data = f.read() if f is not None else b""
    if f is None or len(data) == 0:
        return jsonify(message="Please choose a file to upload."), 400
    if len(data) > CV_MAX_BYTES:
        return jsonify(message="That file is too large. A CV can be up to 2 MB."), 400

    # ASP.NET Core's IFormFile.FileName keeps backslashes exactly as the
    # browser sent them, but Werkzeug treats them as escape characters and
    # drops them ("C:\Users\..." becomes "CUsers..."). Read the name from the
    # raw Content-Disposition header instead, so the path-stripping rule sees
    # the same input it would in the real backend.
    raw_cd = f.headers.get("Content-Disposition", "")
    m = re.search(r'filename="([^"]*)"', raw_cd)
    name = safe_file_name(m.group(1) if m else f.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in CV_TYPES:
        return jsonify(message="Please upload your CV as a " + CV_TYPES_TEXT + "."), 400
    if not data.startswith(CV_SIGNATURES[ext]):
        return jsonify(message="That file does not look like a real " + CV_TYPES_TEXT +
                               ". Please check the file and try again."), 400

    replaced = u["id"] in DB["cvs"]
    DB["cvs"][u["id"]] = {"fileName": name, "contentType": CV_TYPES[ext], "data": data,
                          "uploadedAt": now()}
    return jsonify(message="Your CV has been replaced." if replaced else "Your CV has been uploaded.",
                   fileName=name, sizeBytes=len(data), uploadedAt=DB["cvs"][u["id"]]["uploadedAt"])


def send_cv(uid):
    cv = DB["cvs"].get(uid)
    if not cv:
        return jsonify(message="No CV has been uploaded."), 404
    return Response(cv["data"], mimetype=cv["contentType"],
                    headers={"Content-Disposition": 'attachment; filename="' + cv["fileName"] + '"',
                             "X-Content-Type-Options": "nosniff"})


@app.get("/api/profile/cv")
def download_my_cv():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    return send_cv(u["id"])


@app.get("/api/profile/<int:uid>/cv")
def download_cv(uid):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    allowed = u["id"] == uid or u["role"] == "admin" or any(
        a["workerId"] == uid and
        next(x for x in DB["jobs"] if x["id"] == a["jobId"])["employerId"] == u["id"]
        for a in DB["apps"])
    if not allowed:
        return jsonify(message="Forbidden"), 403
    return send_cv(uid)


@app.delete("/api/profile/cv")
def delete_cv():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    if u["id"] not in DB["cvs"]:
        return jsonify(message="You have not uploaded a CV."), 404
    del DB["cvs"][u["id"]]
    return jsonify(message="Your CV has been removed.")


@app.put("/api/profile")
def update_profile():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter your full name."), 400
    phone = (d.get("phone") or "").strip()
    if not (9 <= sum(c.isdigit() for c in phone) <= 15):
        return jsonify(message="Please enter a valid phone number."), 400
    years = int(d.get("experienceYears") or 0)
    if years < 0 or years > 60:
        return jsonify(message="Years of experience must be between 0 and 60."), 400
    u.update({"name": name, "phone": phone, "skills": (d.get("skills") or "").strip(),
              "location": (d.get("location") or "").strip(),
              "district": (d.get("district") or "").strip(),
              "bio": (d.get("bio") or "").strip(),
              "experience": (d.get("experience") or "").strip(),
              "experienceYears": years,
              "certifications": (d.get("certifications") or "").strip(),
              "available": bool(d.get("available", True))})
    return jsonify(message="Profile updated.")


@app.get("/api/organization")
def get_org():
    u = current_user()
    if not role_in(u, "organization", "employer", "admin"):
        return jsonify(message="Forbidden"), 403
    return jsonify(userId=u["id"], organizationName=u["organizationName"],
                   registrationNumber=u["registrationNumber"], address=u["organizationAddress"],
                   website=u["organizationWebsite"], district=u["district"],
                   notes=u["verificationNotes"], verificationStatus=u["verificationStatus"],
                   requestedAt=u["verificationRequestedAt"], verifiedAt=u["verifiedAt"],
                   decisionNote=u["verificationDecisionNote"])


@app.put("/api/organization")
def put_org():
    u = current_user()
    if not role_in(u, "organization", "employer", "admin"):
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    name = (d.get("organizationName") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter the organization name."), 400
    was_verified = u["verificationStatus"] == "verified"
    changed = (u["organizationName"] != name or
               u["registrationNumber"] != (d.get("registrationNumber") or "").strip())
    u["organizationName"] = name
    u["registrationNumber"] = (d.get("registrationNumber") or "").strip()
    u["organizationAddress"] = (d.get("address") or "").strip()
    u["organizationWebsite"] = (d.get("website") or "").strip()
    if d.get("district"):
        u["district"] = d["district"].strip()
    if was_verified and changed:
        u["verificationStatus"] = "pending"
        u["verificationRequestedAt"] = now()
        u["verifiedAt"] = None
        u["verificationDecisionNote"] = "Details changed after verification; awaiting review."
    return jsonify(message="Details saved. Because the registered details changed, your account is awaiting review again."
                   if was_verified and changed else "Organization details saved.",
                   verificationStatus=u["verificationStatus"])


@app.post("/api/organization/verify")
def request_verify():
    u = current_user()
    if not role_in(u, "organization", "employer", "admin"):
        return jsonify(message="Forbidden"), 403
    if u["verificationStatus"] == "verified":
        return jsonify(message="This account is already verified."), 400
    if u["verificationStatus"] == "pending":
        return jsonify(message="Your request is already waiting for review."), 400
    if not u["organizationName"]:
        return jsonify(message="Please save your organization name before requesting verification."), 400
    if not u["registrationNumber"]:
        return jsonify(message="A business or organization registration number is required."), 400
    d = request.get_json(force=True, silent=True) or {}
    u["verificationStatus"] = "pending"
    u["verificationRequestedAt"] = now()
    u["verificationNotes"] = (d.get("notes") or "").strip()
    u["verificationDecisionNote"] = ""
    for a in DB["users"]:
        if a["role"] == "admin":
            note(a["id"], "verification", "Verification request",
                 f'{u["organizationName"]} requested organization verification.')
    return jsonify(message="Your verification request has been submitted for review.",
                   verificationStatus="pending")


@app.get("/api/categories")
def list_categories():
    inc = request.args.get("includeInactive") in ("true", "True", "1")
    out = []
    for c in sorted(DB["categories"], key=lambda c: (c["sortOrder"], c["name"])):
        if not inc and not c["isActive"]:
            continue
        out.append({**c, "openJobs": sum(1 for j in DB["jobs"]
                                         if j["category"] == c["name"] and j["status"] == "open")})
    return jsonify(out)


@app.post("/api/categories")
def create_category():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter a category name."), 400
    if any(c["name"].lower() == name.lower() for c in DB["categories"]):
        return jsonify(message="That category already exists."), 409
    c = {"id": nid("category"), "name": name, "description": (d.get("description") or "").strip(),
         "icon": d.get("icon") or "fa-briefcase", "sortOrder": int(d.get("sortOrder") or 0),
         "isActive": True, "createdAt": now()}
    DB["categories"].append(c)
    return jsonify(message="Category added.", id=c["id"])


@app.put("/api/categories/<int:cid>")
def update_category(cid):
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    c = next((x for x in DB["categories"] if x["id"] == cid), None)
    if not c:
        return jsonify(message="Category not found."), 404
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter a category name."), 400
    if any(x["id"] != cid and x["name"].lower() == name.lower() for x in DB["categories"]):
        return jsonify(message="Another category already uses that name."), 409
    if c["name"] != name:
        for j in DB["jobs"]:
            if j["category"] == c["name"]:
                j["category"] = name
    c["name"] = name
    c["description"] = (d.get("description") or "").strip()
    if d.get("icon"):
        c["icon"] = d["icon"]
    c["sortOrder"] = int(d.get("sortOrder") or 0)
    if d.get("isActive") is not None:
        c["isActive"] = bool(d["isActive"])
    return jsonify(message="Category updated.")


@app.delete("/api/categories/<int:cid>")
def delete_category(cid):
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    c = next((x for x in DB["categories"] if x["id"] == cid), None)
    if not c:
        return jsonify(message="Category not found."), 404
    in_use = sum(1 for j in DB["jobs"] if j["category"] == c["name"])
    if in_use:
        c["isActive"] = False
        return jsonify(message=f"{in_use} job(s) still use this category, so it was hidden rather than deleted.",
                       action="hidden")
    DB["categories"].remove(c)
    return jsonify(message="Category deleted.", action="deleted")


@app.post("/api/contact")
def contact():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    subject = (d.get("subject") or "").strip()
    body = (d.get("message") or "").strip()
    if len(name) < 2:
        return jsonify(message="Please enter your name."), 400
    if "@" not in email or len(email) < 5:
        return jsonify(message="Please enter a valid email address."), 400
    if len(subject) < 3:
        return jsonify(message="Please enter a subject."), 400
    if len(body) < 10:
        return jsonify(message="Please write a little more detail in your message."), 400
    if (d.get("website") or "").strip():
        return jsonify(message="Thank you. Your message has been received.")
    u = current_user()
    DB["messages"].append({"id": nid("message"), "name": name, "email": email,
                           "subject": subject, "message": body, "status": "new",
                           "userId": u["id"] if u else None, "createdAt": now(),
                           "handledAt": None})
    for a in DB["users"]:
        if a["role"] == "admin":
            note(a["id"], "message", "New contact message", f'{name} wrote about "{subject}".')
    return jsonify(message="Thank you. Your message has been received and our team will reply by email.")


@app.get("/api/notifications")
def list_notes():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    rows = sorted([n for n in DB["notes"] if n["userId"] == u["id"]], key=lambda n: -n["id"])
    return jsonify(rows[:50])


@app.get("/api/notifications/unread-count")
def unread():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    return jsonify(count=sum(1 for n in DB["notes"] if n["userId"] == u["id"] and not n["isRead"]))


@app.put("/api/notifications/read-all")
def read_all():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    for n in DB["notes"]:
        if n["userId"] == u["id"]:
            n["isRead"] = True
    return jsonify(message="All notifications marked as read.")


@app.put("/api/notifications/<int:nid_>/read")
def read_one(nid_):
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    n = next((x for x in DB["notes"] if x["id"] == nid_ and x["userId"] == u["id"]), None)
    if not n:
        return jsonify(message="Notification not found."), 404
    n["isRead"] = True
    return jsonify(message="Marked as read.")


# =====================================================================
# Employer workspace
# =====================================================================
@app.get("/api/employer/stats")
def emp_stats():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    ids = {j["id"] for j in DB["jobs"] if j["employerId"] == u["id"]}
    apps = [a for a in DB["apps"] if a["jobId"] in ids]
    pays = [p for p in DB["payments"] if p["jobId"] in ids]
    return jsonify(myJobs=len(ids),
                   openJobs=sum(1 for j in DB["jobs"] if j["employerId"] == u["id"] and j["status"] == "open"),
                   applicants=len(apps),
                   pendingReview=sum(1 for a in apps if a["status"] == "pending"),
                   shortlisted=sum(1 for a in apps if a["status"] == "shortlisted"),
                   hired=sum(1 for a in apps if a["status"] == "accepted"),
                   completed=sum(1 for a in apps if a["status"] == "completed"),
                   amountOwed=money(sum(p["amount"] - p["amountPaid"] for p in pays)),
                   amountPaid=money(sum(p["amountPaid"] for p in pays)),
                   verificationStatus=u["verificationStatus"],
                   isVerified=u["verificationStatus"] == "verified")


@app.get("/api/employer/jobs")
def emp_jobs():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    out = []
    for j in sorted([j for j in DB["jobs"] if j["employerId"] == u["id"]], key=lambda j: -j["id"]):
        apps = [a for a in DB["apps"] if a["jobId"] == j["id"]]
        out.append({**{k: j[k] for k in ("id", "title", "category", "location", "district",
                                         "per", "urgent", "status", "description",
                                         "requiredSkills", "workersNeeded", "expectedUnits",
                                         "startDate", "endDate", "createdAt", "updatedAt")},
                    "pay": money(j["pay"]),
                    "applications": len(apps),
                    "pending": sum(1 for a in apps if a["status"] == "pending"),
                    "shortlisted": sum(1 for a in apps if a["status"] == "shortlisted"),
                    "hired": sum(1 for a in apps if a["status"] == "accepted"),
                    "completed": sum(1 for a in apps if a["status"] == "completed")})
    return jsonify(out)


@app.get("/api/employer/applicants")
def emp_applicants():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    ids = {j["id"] for j in DB["jobs"] if j["employerId"] == u["id"]}
    out = []
    for a in sorted([a for a in DB["apps"] if a["jobId"] in ids], key=lambda a: -a["id"]):
        j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
        w = user_by_id(a["workerId"]) or {}
        out.append({"id": a["id"], "jobId": a["jobId"], "jobTitle": j["title"],
                    "workerId": a["workerId"], "workerName": w.get("name", ""),
                    "workerPhone": w.get("phone", ""), "workerEmail": w.get("email", ""),
                    "workerSkills": w.get("skills", ""),
                    "workerExperience": w.get("experience", ""),
                    "workerExperienceYears": w.get("experienceYears", 0),
                    "workerLocation": w.get("location", ""),
                    "workerRating": avg_stars(a["workerId"]),
                    "workerJobsCompleted": sum(1 for x in DB["apps"]
                                               if x["workerId"] == a["workerId"] and x["status"] == "completed"),
                    "workerHasCv": a["workerId"] in DB["cvs"],
                    "workerCvFileName": DB["cvs"].get(a["workerId"], {}).get("fileName", ""),
                    "message": a.get("message", ""), "status": a["status"],
                    "createdAt": a["createdAt"]})
    return jsonify(out)


@app.get("/api/employer/payments")
def emp_payments():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    ids = {j["id"] for j in DB["jobs"] if j["employerId"] == u["id"]}
    rows = [p for p in DB["payments"] if p["jobId"] in ids]
    rows.sort(key=lambda p: (p["status"] == "paid", -p["id"]))
    return jsonify([payment_dto(p, for_worker=False) for p in rows])


# =====================================================================
# Reports
# =====================================================================
def by_month(items, keyfn, valfn=None):
    buckets = {}
    for it in items:
        d = keyfn(it)[:7]
        buckets.setdefault(d, []).append(it)
    out = []
    for k in sorted(buckets):
        y, m = k.split("-")
        label = datetime.date(int(y), int(m), 1).strftime("%b %Y")
        out.append({"month": k, "label": label, "items": buckets[k]})
    return out


@app.get("/api/reports/worker")
def rep_worker():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    apps = [a for a in DB["apps"] if a["workerId"] == u["id"]]
    pays = [p for p in DB["payments"] if p["workerId"] == u["id"]]
    stars = [r["stars"] for r in DB["ratings"] if r["subjectId"] == u["id"]]
    ebm = [{"month": b["month"], "label": b["label"],
            "amount": money(sum(p["amountPaid"] for p in b["items"])),
            "jobs": len(b["items"])}
           for b in by_month([p for p in pays if p["amountPaid"] > 0],
                             lambda p: p["paidAt"] or p["createdAt"])]
    cats = {}
    for a in apps:
        if a["status"] == "completed":
            j = next(x for x in DB["jobs"] if x["id"] == a["jobId"])
            cats[j["category"]] = cats.get(j["category"], 0) + 1
    return jsonify(applied=len(apps),
                   pending=sum(1 for a in apps if a["status"] == "pending"),
                   shortlisted=sum(1 for a in apps if a["status"] == "shortlisted"),
                   hired=sum(1 for a in apps if a["status"] == "accepted"),
                   completed=sum(1 for a in apps if a["status"] == "completed"),
                   rejected=sum(1 for a in apps if a["status"] == "rejected"),
                   successRate=round(sum(1 for a in apps if a["status"] in ("accepted", "completed")) * 100 / len(apps), 1) if apps else 0,
                   totalEarned=money(sum(p["amountPaid"] for p in pays)),
                   pendingWages=money(sum(p["amount"] - p["amountPaid"] for p in pays)),
                   paymentRecords=len(pays),
                   awaitingConfirmation=sum(1 for p in pays if p["amountPaid"] > 0 and not p["workerConfirmed"]),
                   averageRating=round(sum(stars) / len(stars), 1) if stars else 0,
                   ratingCount=len(stars), earningsByMonth=ebm,
                   byCategory=[{"category": k, "jobs": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])])


@app.get("/api/reports/employer")
def rep_employer():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    jobs = [j for j in DB["jobs"] if j["employerId"] == u["id"]]
    ids = {j["id"] for j in jobs}
    apps = [a for a in DB["apps"] if a["jobId"] in ids]
    pays = [p for p in DB["payments"] if p["jobId"] in ids]
    pbm = [{"month": b["month"], "label": b["label"], "posted": len(b["items"])}
           for b in by_month(jobs, lambda j: j["createdAt"])]
    sbm = [{"month": b["month"], "label": b["label"],
            "amount": money(sum(p["amountPaid"] for p in b["items"]))}
           for b in by_month([p for p in pays if p["amountPaid"] > 0],
                             lambda p: p["paidAt"] or p["createdAt"])]
    cats = {}
    for j in jobs:
        cats.setdefault(j["category"], {"posted": 0, "applicants": 0})
        cats[j["category"]]["posted"] += 1
        cats[j["category"]]["applicants"] += sum(1 for a in apps if a["jobId"] == j["id"])
    return jsonify(jobsPosted=len(jobs),
                   openJobs=sum(1 for j in jobs if j["status"] == "open"),
                   closedJobs=sum(1 for j in jobs if j["status"] == "closed"),
                   totalApplicants=len(apps),
                   pendingReview=sum(1 for a in apps if a["status"] == "pending"),
                   shortlisted=sum(1 for a in apps if a["status"] == "shortlisted"),
                   hired=sum(1 for a in apps if a["status"] == "accepted"),
                   completed=sum(1 for a in apps if a["status"] == "completed"),
                   rejected=sum(1 for a in apps if a["status"] == "rejected"),
                   fillRate=round(sum(1 for a in apps if a["status"] in ("accepted", "completed")) * 100 /
                                  max(sum(j["workersNeeded"] for j in jobs), 1), 1),
                   averageApplicantsPerJob=round(len(apps) / len(jobs), 1) if jobs else 0,
                   totalSpent=money(sum(p["amountPaid"] for p in pays)),
                   outstanding=money(sum(p["amount"] - p["amountPaid"] for p in pays)),
                   paymentRecords=len(pays), postingsByMonth=pbm, spendByMonth=sbm,
                   byCategory=[{"category": k, **v} for k, v in sorted(cats.items(), key=lambda x: -x[1]["posted"])])


@app.get("/api/reports/admin")
def rep_admin():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    users, jobs, apps, pays = DB["users"], DB["jobs"], DB["apps"], DB["payments"]
    cats = {}
    for j in jobs:
        cats[j["category"]] = cats.get(j["category"], 0) + 1
    return jsonify(totalUsers=len(users),
                   activeUsers=sum(1 for u2 in users if u2.get("isActive", True)),
                   byRole={"workers": sum(1 for x in users if x["role"] == "worker"),
                           "employers": sum(1 for x in users if x["role"] == "employer"),
                           "organizations": sum(1 for x in users if x["role"] == "organization"),
                           "admins": sum(1 for x in users if x["role"] == "admin")},
                   verification={"verified": sum(1 for x in users if x["verificationStatus"] == "verified"),
                                 "pending": sum(1 for x in users if x["verificationStatus"] == "pending"),
                                 "rejected": sum(1 for x in users if x["verificationStatus"] == "rejected"),
                                 "unverified": sum(1 for x in users if x["verificationStatus"] == "unverified")},
                   jobsPosted=len(jobs),
                   openJobs=sum(1 for j in jobs if j["status"] == "open"),
                   applications=len(apps),
                   completedJobs=sum(1 for a in apps if a["status"] == "completed"),
                   payments={"records": len(pays), "totalDue": money(sum(p["amount"] for p in pays)),
                             "totalPaid": money(sum(p["amountPaid"] for p in pays)),
                             "outstanding": money(sum(p["amount"] - p["amountPaid"] for p in pays))},
                   jobsByCategory=[{"category": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])],
                   signupsByMonth=[{"month": b["month"], "label": b["label"], "users": len(b["items"])}
                                   for b in by_month(users, lambda u2: u2["createdAt"])],
                   jobsByMonth=[{"month": b["month"], "label": b["label"], "posted": len(b["items"])}
                                for b in by_month(jobs, lambda j: j["createdAt"])],
                   newMessages=sum(1 for m in DB["messages"] if m["status"] == "new"))


def csv_text(header, rows):
    def esc(v):
        v = "" if v is None else str(v)
        return '"' + v.replace('"', '""') + '"' if any(c in v for c in ',"\n') else v
    return header + "\n" + "\n".join(",".join(esc(c) for c in r) for r in rows) + "\n"


def csv_response(header, rows, filename):
    return Response(csv_text(header, rows), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def worker_payment_rows(uid):
    rows = []
    for p in [p for p in DB["payments"] if p["workerId"] == uid]:
        j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
        emp = user_by_id(j["employerId"]) or {}
        rows.append([j["title"], emp.get("name", ""), f'{p["agreedRate"]:.2f}', p["rateUnit"],
                     p["unitsWorked"], f'{p["amount"]:.2f}', f'{p["amountPaid"]:.2f}',
                     f'{p["amount"] - p["amountPaid"]:.2f}', p["status"],
                     "yes" if p["workerConfirmed"] else "no",
                     p["createdAt"][:10], (p["paidAt"] or "")[:10]])
    return rows


def employer_payment_rows(uid):
    ids = {j["id"] for j in DB["jobs"] if j["employerId"] == uid}
    rows = []
    for p in [p for p in DB["payments"] if p["jobId"] in ids]:
        j = next(x for x in DB["jobs"] if x["id"] == p["jobId"])
        w = user_by_id(p["workerId"]) or {}
        rows.append([j["title"], w.get("name", ""), f'{p["agreedRate"]:.2f}', p["rateUnit"],
                     p["unitsWorked"], f'{p["amount"]:.2f}', f'{p["amountPaid"]:.2f}',
                     f'{p["amount"] - p["amountPaid"]:.2f}', p["status"],
                     "yes" if p["workerConfirmed"] else "no",
                     p["createdAt"][:10], (p["paidAt"] or "")[:10]])
    return rows


def admin_job_rows():
    rows = []
    for j in DB["jobs"]:
        emp = user_by_id(j["employerId"]) or {}
        rows.append([j["id"], j["title"], j["category"], j["location"], j["district"],
                     f'{j["pay"]:.2f}', j["per"], j["workersNeeded"], j["status"],
                     emp.get("name", ""),
                     sum(1 for a in DB["apps"] if a["jobId"] == j["id"]), j["createdAt"][:10]])
    return rows


WORKER_CSV_HEAD = "Job,Employer,Rate,Unit,UnitsWorked,AmountDue,AmountPaid,Outstanding,Status,Confirmed,RaisedOn,PaidOn"
EMPLOYER_CSV_HEAD = "Job,Worker,Rate,Unit,UnitsWorked,AmountDue,AmountPaid,Outstanding,Status,WorkerConfirmed,RaisedOn,PaidOn"
JOBS_CSV_HEAD = "Id,Title,Category,Location,District,Rate,Unit,WorkersNeeded,Status,Employer,Applicants,PostedOn"


# ---------------------------------------------------------------------
# POST /api/reports/email (mirrors ReportsController.EmailReport)
# ---------------------------------------------------------------------
@app.post("/api/reports/email")
def email_report():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    d = request.get_json(silent=True) or {}
    kind = (d.get("report") or "").strip().lower()
    is_admin = u["role"] == "admin"
    employer_side = is_admin or u["role"] in ("employer", "organization")

    if kind not in ("worker", "employer", "admin"):
        return jsonify(message="Please choose which report to send."), 400
    if kind == "admin" and not is_admin:
        return jsonify(message="Forbidden"), 403
    if kind == "employer" and not employer_side:
        return jsonify(message="Forbidden"), 403

    delivery = delivery_for(u["email"])
    if delivery == "off":
        if is_demo(u["email"]) and MAIL_MODE == "smtp":
            return jsonify(message="This is a demonstration account, and its email address (" + u["email"] +
                                   ") is not a real mailbox, so the report cannot be emailed to it. "
                                   "You can still download it with the Export button."), 400
        return jsonify(message="Email has not been set up on this server yet, so the report could not be "
                               "sent. You can still download it with the Export button."), 503

    # one report a minute per user
    last = LAST_REPORT.get(u["id"])
    nowt = datetime.datetime.utcnow()
    if last is not None and (nowt - last).total_seconds() < 60:
        wait = int(-(-(60 - (nowt - last).total_seconds()) // 1))
        return jsonify(message="A report was sent a moment ago. Please wait " + str(wait) +
                               " seconds before sending another."), 429
    LAST_REPORT[u["id"]] = nowt

    def pct(x):
        return (f"{round(x, 1):.1f}".rstrip("0").rstrip(".")) + "%"

    if kind == "admin":
        title = "DailyWork platform report"
        users, jobs, apps, pays = DB["users"], DB["jobs"], DB["apps"], DB["payments"]
        figures = [("Total users", str(len(users))),
                   ("Active users", str(sum(1 for x in users if x.get("isActive", True)))),
                   ("Workers", str(sum(1 for x in users if x["role"] == "worker"))),
                   ("Employers", str(sum(1 for x in users if x["role"] == "employer"))),
                   ("Organizations", str(sum(1 for x in users if x["role"] == "organization"))),
                   ("Jobs posted", str(len(jobs))),
                   ("Open jobs", str(sum(1 for j in jobs if j["status"] == "open"))),
                   ("Applications", str(len(apps))),
                   ("Jobs completed", str(sum(1 for a in apps if a["status"] == "completed"))),
                   ("Payment records", str(len(pays))),
                   ("Total paid", rs(sum(p["amountPaid"] for p in pays))),
                   ("Outstanding", rs(sum(p["amount"] - p["amountPaid"] for p in pays)))]
        # The users list is deliberately not attached: it holds everyone's contact details.
        files = [("dailywork-jobs.csv", csv_text(JOBS_CSV_HEAD, admin_job_rows()))]
    elif kind == "employer":
        title = "Your DailyWork hiring report"
        jobs = [j for j in DB["jobs"] if j["employerId"] == u["id"]]
        ids = {j["id"] for j in jobs}
        st = [a["status"] for a in DB["apps"] if a["jobId"] in ids]
        pays = [p for p in DB["payments"] if p["jobId"] in ids]
        filled = sum(1 for x in st if x in ("accepted", "completed"))
        fill = filled * 100.0 / max(sum(j["workersNeeded"] for j in jobs), 1) if jobs else 0
        figures = [("Jobs posted", str(len(jobs))),
                   ("Open jobs", str(sum(1 for j in jobs if j["status"] == "open"))),
                   ("Total applicants", str(len(st))),
                   ("Awaiting your review", str(st.count("pending"))),
                   ("Shortlisted", str(st.count("shortlisted"))),
                   ("Currently hired", str(st.count("accepted"))),
                   ("Jobs completed", str(st.count("completed"))),
                   ("Positions filled", pct(fill)),
                   ("Total paid to workers", rs(sum(p["amountPaid"] for p in pays))),
                   ("Still outstanding", rs(sum(p["amount"] - p["amountPaid"] for p in pays)))]
        files = [("dailywork-employer-payments.csv",
                  csv_text(EMPLOYER_CSV_HEAD, employer_payment_rows(u["id"])))]
    else:
        title = "Your DailyWork work report"
        st = [a["status"] for a in DB["apps"] if a["workerId"] == u["id"]]
        pays = [p for p in DB["payments"] if p["workerId"] == u["id"]]
        won = sum(1 for x in st if x in ("accepted", "completed"))
        figures = [("Jobs applied for", str(len(st))),
                   ("Waiting for a decision", str(st.count("pending"))),
                   ("Shortlisted", str(st.count("shortlisted"))),
                   ("Currently hired", str(st.count("accepted"))),
                   ("Jobs completed", str(st.count("completed"))),
                   ("Not successful", str(st.count("rejected"))),
                   ("Success rate", pct(won * 100.0 / len(st) if st else 0)),
                   ("Total earned", rs(sum(p["amountPaid"] for p in pays))),
                   ("Wages still owed to you", rs(sum(p["amount"] - p["amountPaid"] for p in pays)))]
        files = [("dailywork-payments.csv", csv_text(WORKER_CSV_HEAD, worker_payment_rows(u["id"])))]

    today = datetime.datetime.utcnow().strftime("%-d %b %Y")
    queued = queue_email("report_" + kind, u["email"], u["name"], title + " - " + today, figures,
                         [{"fileName": n, "contentType": "text/csv",
                           "data": b"\xef\xbb\xbf" + t.encode("utf-8")} for n, t in files])
    if not queued:
        return jsonify(message="The report could not be sent just now. Please try again in a minute."), 503

    if delivery == "outbox":
        why = ("This is a demonstration account without a real mailbox" if is_demo(u["email"])
               else "This server is not connected to a mail server yet")
        return jsonify(delivery="outbox",
                       message=why + ", so your report was saved in the server's email outbox folder "
                                     "instead of being sent.")
    return jsonify(delivery="smtp", message="Your report is on its way to " + u["email"] + ".")


# ---------------------------------------------------------------------
# TEST HOOK ONLY (no equivalent in the C# API): lets the tests read the
# emails this server recorded, and clear them between sections.
# ---------------------------------------------------------------------
@app.get("/api/_test/emails")
def test_emails():
    return jsonify(DB["emails"])


@app.delete("/api/_test/emails")
def test_emails_clear():
    DB["emails"].clear()
    LAST_REPORT.clear()
    return jsonify(message="cleared")


@app.get("/api/reports/worker/payments.csv")
def csv_worker():
    u = current_user()
    if not u:
        return jsonify(message="Unauthorized"), 401
    return csv_response(WORKER_CSV_HEAD, worker_payment_rows(u["id"]), "dailywork-payments.csv")


@app.get("/api/reports/employer/payments.csv")
def csv_employer():
    u = current_user()
    if not role_in(u, "employer", "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    return csv_response(EMPLOYER_CSV_HEAD, employer_payment_rows(u["id"]),
                        "dailywork-employer-payments.csv")


@app.get("/api/reports/admin/users.csv")
def csv_users():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    rows = [[x["id"], x["name"], x["email"], x["phone"], x["role"], x["district"],
             "yes" if x.get("isActive", True) else "no", x["verificationStatus"],
             x["createdAt"][:10]] for x in DB["users"]]
    return csv_response("Id,Name,Email,Phone,Role,District,Active,VerificationStatus,JoinedOn",
                        rows, "dailywork-users.csv")


@app.get("/api/reports/admin/jobs.csv")
def csv_jobs():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    return csv_response(JOBS_CSV_HEAD, admin_job_rows(), "dailywork-jobs.csv")


# =====================================================================
# Admin
# =====================================================================
def need_admin():
    u = current_user()
    return u if (u and u["role"] == "admin") else None


@app.get("/api/admin/stats")
def admin_stats():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    pays = DB["payments"]
    return jsonify(totalUsers=len(DB["users"]),
                   activeUsers=sum(1 for x in DB["users"] if x.get("isActive", True)),
                   workers=sum(1 for x in DB["users"] if x["role"] == "worker"),
                   employers=sum(1 for x in DB["users"] if x["role"] == "employer"),
                   organizations=sum(1 for x in DB["users"] if x["role"] == "organization"),
                   admins=sum(1 for x in DB["users"] if x["role"] == "admin"),
                   totalJobs=len(DB["jobs"]),
                   openJobs=sum(1 for j in DB["jobs"] if j["status"] == "open"),
                   applications=len(DB["apps"]),
                   completedJobs=sum(1 for a in DB["apps"] if a["status"] == "completed"),
                   payments=len(pays), paidAmount=money(sum(p["amountPaid"] for p in pays)),
                   outstanding=money(sum(p["amount"] - p["amountPaid"] for p in pays)),
                   pendingVerifications=sum(1 for x in DB["users"] if x["verificationStatus"] == "pending"),
                   newMessages=sum(1 for m in DB["messages"] if m["status"] == "new"))


@app.get("/api/admin/users")
def admin_users():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    return jsonify([{"id": x["id"], "name": x["name"], "email": x["email"], "phone": x["phone"],
                     "role": x["role"], "createdAt": x["createdAt"],
                     "isActive": x.get("isActive", True),
                     "verificationStatus": x["verificationStatus"],
                     "district": x["district"], "location": x["location"]}
                    for x in sorted(DB["users"], key=lambda x: -x["id"])])


@app.put("/api/admin/users/<int:uid>/role")
def admin_role(uid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    if d.get("role") not in ("worker", "employer", "organization", "admin"):
        return jsonify(message="Invalid role."), 400
    t = user_by_id(uid)
    if not t:
        return jsonify(message="User not found."), 404
    if t["role"] == d["role"]:
        return jsonify(message=f'This user is already a {d["role"]}.'), 400
    if t["role"] == "admin" and d["role"] != "admin" and \
       sum(1 for x in DB["users"] if x["role"] == "admin" and x.get("isActive", True)) <= 1:
        return jsonify(message="Cannot demote the last remaining administrator."), 400
    t["role"] = d["role"]
    t["securityStamp"] = str(int(t.get("securityStamp", "1")) + 1)
    if d["role"] not in ("organization", "employer") and t["verificationStatus"] == "verified":
        t["verificationStatus"] = "unverified"
        t["verifiedAt"] = None
    return jsonify(message="Role updated. The user must sign in again.")


@app.delete("/api/admin/users/<int:uid>")
def admin_delete_user(uid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    t = user_by_id(uid)
    if not t:
        return jsonify(message="User not found."), 404
    if t["id"] == u["id"]:
        return jsonify(message="You cannot remove your own account."), 400
    if t["role"] == "admin" and \
       sum(1 for x in DB["users"] if x["role"] == "admin" and x.get("isActive", True)) <= 1:
        return jsonify(message="Cannot delete the last remaining administrator."), 400

    has_history = (any(p["workerId"] == uid for p in DB["payments"]) or
                   any(r["authorId"] == uid or r["subjectId"] == uid for r in DB["ratings"]) or
                   any(w["workerId"] == uid for w in DB["work"]) or
                   any(j["employerId"] == uid for j in DB["jobs"]))

    if has_history:
        if not t.get("isActive", True):
            return jsonify(message="This account is already deactivated."), 400
        t["isActive"] = False
        t["deactivatedAt"] = now()
        t["securityStamp"] = str(int(t.get("securityStamp", "1")) + 1)
        for j in DB["jobs"]:
            if j["employerId"] == uid and j["status"] == "open":
                j["status"] = "closed"
        return jsonify(message="This account holds payment or review history, so it was deactivated instead of deleted. The financial records stay intact.",
                       action="deactivated")

    DB["apps"][:] = [a for a in DB["apps"] if a["workerId"] != uid]
    DB["notes"][:] = [n for n in DB["notes"] if n["userId"] != uid]
    DB["cvs"].pop(uid, None)          # ON DELETE CASCADE on CvDocuments
    DB["users"].remove(t)
    return jsonify(message="User deleted.", action="deleted")


@app.put("/api/admin/users/<int:uid>/reactivate")
def admin_reactivate(uid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    t = user_by_id(uid)
    if not t:
        return jsonify(message="User not found."), 404
    if t.get("isActive", True):
        return jsonify(message="This account is already active."), 400
    t["isActive"] = True
    t["securityStamp"] = str(int(t.get("securityStamp", "1")) + 1)
    return jsonify(message="Account reactivated.")


@app.get("/api/admin/jobs")
def admin_jobs():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    out = []
    for j in sorted(DB["jobs"], key=lambda j: -j["id"]):
        emp = user_by_id(j["employerId"]) or {}
        out.append({"id": j["id"], "title": j["title"], "category": j["category"],
                    "location": j["location"], "pay": money(j["pay"]), "per": j["per"],
                    "status": j["status"], "urgent": j["urgent"],
                    "workersNeeded": j["workersNeeded"],
                    "employerName": emp.get("name", ""),
                    "employerVerified": emp.get("verificationStatus") == "verified",
                    "applications": sum(1 for a in DB["apps"] if a["jobId"] == j["id"]),
                    "createdAt": j["createdAt"]})
    return jsonify(out)


@app.delete("/api/admin/jobs/<int:jid>")
def admin_delete_job(jid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    j = next((x for x in DB["jobs"] if x["id"] == jid), None)
    if not j:
        return jsonify(message="Job not found."), 404
    has = (any(p["jobId"] == jid for p in DB["payments"]) or
           any(a["jobId"] == jid and a["status"] == "completed" for a in DB["apps"]))
    if has:
        if j["status"] == "closed":
            return jsonify(message="This job is already closed."), 400
        j["status"] = "closed"
        return jsonify(message="This job has completed work and payment records attached, so it was closed instead of deleted.",
                       action="closed")
    DB["apps"][:] = [a for a in DB["apps"] if a["jobId"] != jid]
    DB["jobs"].remove(j)
    return jsonify(message="Job deleted.", action="deleted")


@app.get("/api/admin/verifications")
def admin_verifications():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    want = (request.args.get("status") or "pending").lower()
    rows = []
    for x in DB["users"]:
        if want == "all":
            if x["verificationStatus"] == "unverified":
                continue
        elif x["verificationStatus"] != want:
            continue
        rows.append({"userId": x["id"], "name": x["name"], "email": x["email"],
                     "phone": x["phone"], "role": x["role"],
                     "organizationName": x["organizationName"],
                     "registrationNumber": x["registrationNumber"],
                     "organizationAddress": x["organizationAddress"],
                     "organizationWebsite": x["organizationWebsite"],
                     "notes": x["verificationNotes"], "status": x["verificationStatus"],
                     "requestedAt": x["verificationRequestedAt"],
                     "decisionNote": x["verificationDecisionNote"]})
    return jsonify(rows)


@app.put("/api/admin/verifications/<int:uid>")
def admin_decide(uid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    t = user_by_id(uid)
    if not t:
        return jsonify(message="User not found."), 404
    if t["verificationStatus"] != "pending":
        return jsonify(message="There is no pending verification request for this account."), 400
    d = request.get_json(force=True)
    if d.get("approve"):
        t["verificationStatus"] = "verified"
        t["verifiedAt"] = now()
        t["verificationDecisionNote"] = (d.get("note") or "").strip()
        note(uid, "verification", "Your organization has been verified",
             "Your account now shows a verified badge on your job postings.")
    else:
        n = (d.get("note") or "").strip()
        if len(n) < 5:
            return jsonify(message="Please give a reason when rejecting a request."), 400
        t["verificationStatus"] = "rejected"
        t["verificationDecisionNote"] = n
        t["verifiedAt"] = None
        note(uid, "verification", "Verification request declined",
             f"Your verification request was not approved: {n}")
    return jsonify(message="Organization verified." if d.get("approve") else "Request rejected.")


@app.get("/api/admin/messages")
def admin_messages():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    return jsonify(sorted(DB["messages"], key=lambda m: -m["id"]))


@app.put("/api/admin/messages/<int:mid>")
def admin_message(mid):
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    st = (d.get("status") or "").lower()
    if st not in ("new", "read", "answered"):
        return jsonify(message="Invalid status."), 400
    m = next((x for x in DB["messages"] if x["id"] == mid), None)
    if not m:
        return jsonify(message="Message not found."), 404
    m["status"] = st
    m["handledAt"] = None if st == "new" else now()
    return jsonify(message="Message updated.")


@app.post("/api/admin/announce")
def admin_announce():
    u = need_admin()
    if not u:
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True)
    title = (d.get("title") or "").strip()
    body = (d.get("message") or "").strip()
    if len(title) < 3 or len(body) < 5:
        return jsonify(message="Please enter a title and a message."), 400
    aud = (d.get("audience") or "all").lower()
    if aud not in ("all", "worker", "employer", "organization"):
        return jsonify(message="Invalid audience."), 400
    n = 0
    for x in DB["users"]:
        if x.get("isActive", True) and (aud == "all" or x["role"] == aud):
            note(x["id"], "announcement", title, body)
            n += 1
    return jsonify(message=f"Announcement sent to {n} user(s).")



# =====================================================================
# Organization projects and recruitment tracking
# =====================================================================
@app.get("/api/projects")
def list_projects():
    u = current_user()
    if not role_in(u, "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    rows = []
    for pr in sorted([x for x in DB["projects"] if x["organizationId"] == u["id"]],
                     key=lambda x: -x["id"]):
        jobs = [j for j in DB["jobs"] if j.get("projectId") == pr["id"]]
        jids = {j["id"] for j in jobs}
        apps = [a for a in DB["apps"] if a["jobId"] in jids]
        pays = [x for x in DB["payments"] if x["jobId"] in jids]

        hired = sum(1 for a in apps if a["status"] in ("accepted", "completed"))
        positions = sum(j.get("workersNeeded", 1) for j in jobs)
        required = pr["workersRequired"] or positions
        committed = money(sum(x["amount"] for x in pays))
        paid = money(sum(x["amountPaid"] for x in pays))

        rows.append({
            "id": pr["id"], "name": pr["name"], "description": pr["description"],
            "location": pr["location"], "district": pr["district"], "status": pr["status"],
            "startDate": pr["startDate"], "endDate": pr["endDate"],
            "budget": money(pr["budget"]), "createdAt": pr["createdAt"],
            "workersRequired": required, "positionsPosted": positions,
            "jobsPosted": len(jobs), "openJobs": sum(1 for j in jobs if j["status"] == "open"),
            "applicants": len(apps),
            "shortlisted": sum(1 for a in apps if a["status"] == "shortlisted"),
            "hired": hired,
            "completed": sum(1 for a in apps if a["status"] == "completed"),
            "stillNeeded": max(0, required - hired),
            "fillRate": round(hired * 100.0 / required, 1) if required else 0,
            "committed": committed, "paid": paid, "outstanding": money(committed - paid),
            "budgetUsed": round(committed / pr["budget"] * 100, 1) if pr["budget"] else 0,
            "overBudget": bool(pr["budget"] and committed > pr["budget"]),
            "jobs": [{"id": j["id"], "title": j["title"], "status": j["status"],
                      "location": j["location"], "pay": money(j["pay"]), "per": j["per"],
                      "workersNeeded": j.get("workersNeeded", 1),
                      "applicants": sum(1 for a in DB["apps"] if a["jobId"] == j["id"]),
                      "hired": sum(1 for a in DB["apps"] if a["jobId"] == j["id"]
                                   and a["status"] in ("accepted", "completed"))}
                     for j in sorted(jobs, key=lambda x: -x["id"])]
        })

    return jsonify(projects=rows, summary={
        "total": len(rows),
        "active": sum(1 for r in rows if r["status"] == "active"),
        "completed": sum(1 for r in rows if r["status"] == "completed"),
        "workersRequired": sum(r["workersRequired"] for r in rows),
        "hired": sum(r["hired"] for r in rows),
        "stillNeeded": sum(r["stillNeeded"] for r in rows),
        "committed": money(sum(r["committed"] for r in rows)),
        "paid": money(sum(r["paid"] for r in rows)),
        "outstanding": money(sum(r["outstanding"] for r in rows))})


def _proj_status(s):
    s = (s or "").strip().lower()
    return s if s in ("planning", "active", "completed", "cancelled") else "planning"


@app.post("/api/projects")
def create_project():
    u = current_user()
    if not role_in(u, "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True, silent=True) or {}
    name = (d.get("name") or "").strip()
    if len(name) < 3:
        return jsonify(message="Give the project a name of at least 3 characters."), 400
    if (d.get("workersRequired") or 0) < 0 or (d.get("workersRequired") or 0) > 10000:
        return jsonify(message="The number of workers required is not valid."), 400
    if (d.get("budget") or 0) < 0:
        return jsonify(message="The budget cannot be negative."), 400
    if d.get("startDate") and d.get("endDate") and d["endDate"] < d["startDate"]:
        return jsonify(message="The end date cannot be before the start date."), 400

    pr = {"id": nid("project"), "organizationId": u["id"], "name": name,
          "description": (d.get("description") or "").strip(),
          "location": (d.get("location") or "").strip(),
          "district": (d.get("district") or "").strip(),
          "workersRequired": int(d.get("workersRequired") or 0),
          "budget": money(d.get("budget") or 0),
          "startDate": d.get("startDate"), "endDate": d.get("endDate"),
          "status": _proj_status(d.get("status")), "createdAt": now(), "updatedAt": None}
    DB["projects"].append(pr)
    return jsonify(message="Project created.", id=pr["id"])


@app.put("/api/projects/<int:prid>")
def update_project(prid):
    u = current_user()
    if not role_in(u, "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    pr = next((x for x in DB["projects"] if x["id"] == prid), None)
    if not pr:
        return jsonify(message="Project not found."), 404
    if pr["organizationId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    d = request.get_json(force=True, silent=True) or {}
    if d.get("name") is not None:
        if len((d["name"] or "").strip()) < 3:
            return jsonify(message="Give the project a name of at least 3 characters."), 400
        pr["name"] = d["name"].strip()
    if d.get("startDate") and d.get("endDate") and d["endDate"] < d["startDate"]:
        return jsonify(message="The end date cannot be before the start date."), 400
    for k in ("description", "location", "district"):
        if d.get(k) is not None:
            pr[k] = (d[k] or "").strip()
    if d.get("workersRequired"):
        pr["workersRequired"] = int(d["workersRequired"])
    if d.get("budget"):
        pr["budget"] = money(d["budget"])
    if d.get("startDate"):
        pr["startDate"] = d["startDate"]
    if d.get("endDate"):
        pr["endDate"] = d["endDate"]
    if d.get("status"):
        pr["status"] = _proj_status(d["status"])
    pr["updatedAt"] = now()
    return jsonify(message="Project updated.")


@app.delete("/api/projects/<int:prid>")
def delete_project(prid):
    u = current_user()
    if not role_in(u, "organization", "admin"):
        return jsonify(message="Forbidden"), 403
    pr = next((x for x in DB["projects"] if x["id"] == prid), None)
    if not pr:
        return jsonify(message="Project not found."), 404
    if pr["organizationId"] != u["id"] and u["role"] != "admin":
        return jsonify(message="Forbidden"), 403
    kept = [j for j in DB["jobs"] if j.get("projectId") == prid]
    for j in kept:
        j["projectId"] = None
    DB["projects"].remove(pr)
    return jsonify(message=(f"Project removed. {len(kept)} job posting(s) were kept and no "
                            "longer belong to a project.") if kept else "Project removed.")


# =====================================================================
# Public stats + static site
# =====================================================================
@app.get("/api/stats")
def stats():
    real = sum(1 for u in DB["users"] if not u["email"].endswith("@dailywork.lk"))
    demo = sum(1 for u in DB["users"] if u["email"].endswith("@dailywork.lk"))
    return jsonify(workers=sum(1 for u in DB["users"] if u["role"] == "worker" and u.get("isActive", True)),
                   employers=sum(1 for u in DB["users"] if u["role"] in ("employer", "organization") and u.get("isActive", True)),
                   verifiedEmployers=sum(1 for u in DB["users"] if u["verificationStatus"] == "verified"),
                   jobsPosted=len(DB["jobs"]),
                   openJobs=sum(1 for j in DB["jobs"] if j["status"] == "open"),
                   applications=len(DB["apps"]),
                   jobsCompleted=sum(1 for a in DB["apps"] if a["status"] == "completed"),
                   totalPaid=money(sum(p["amountPaid"] for p in DB["payments"])),
                   isDemoData=demo > 0, demoUserCount=demo, realUserCount=real)


@app.get("/")
def index():
    return send_from_directory(WWWROOT, "index.html")


@app.get("/<path:p>")
def static_files(p):
    return send_from_directory(WWWROOT, p)


if __name__ == "__main__":
    seed()
    app.run(port=5000, debug=False, use_reloader=False)
