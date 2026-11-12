"""
Browser test of the CV upload, the role-based Plans menu, and the emails,
driving the real React build in Chromium the way a person would.

    M. Plans / Pricing links are shown to the right roles only
    N. A worker uploads, downloads, replaces and removes their CV
    O. An employer downloads an applicant's CV
    P. Applying, hiring and posting a job each send their emails
    Q. "Email me this report" for worker, employer and administrator

Run against the mirror server (see TEST-RESULTS.md). The mirror records the
emails the system would send, which is how section P and Q check them.

    python test_ui_cv_email.py [screenshot-folder]
"""
from playwright.sync_api import sync_playwright
import os, sys, tempfile, requests

U = "http://localhost:5000/"
API = U + "api"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "dailywork-shots")
WORK = tempfile.mkdtemp(prefix="dailywork-cv-")
os.makedirs(OUT, exist_ok=True)
fails, errs, missing, dialogs = [], [], [], []

PW = "Secret@123"
PDF_A = b"%PDF-1.4\n% browser test CV\n" + b"A" * 6000 + b"\n%%EOF\n"
PDF_B = b"%PDF-1.7\n% replacement CV\n" + b"B" * 150000 + b"\n%%EOF\n"


def write(name, data):
    path = os.path.join(WORK, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


CV_FILE = write("Kamal Perera CV.pdf", PDF_A)
CV_NEW = write("Kamal CV 2026.pdf", PDF_B)
TXT_FILE = write("notes.txt", b"not a CV")
BIG_FILE = write("too-big.pdf", b"%PDF-1.4\n" + b"X" * (2 * 1024 * 1024 + 10))
FAKE_PDF = write("renamed.pdf", b"MZ this is a program, not a PDF" + b"\x00" * 300)


def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -> " + str(detail)[:90]) if detail else ""))
    if not ok:
        fails.append(label)


def api_register(name, email, role):
    r = requests.post(API + "/auth/register", json={"name": name, "email": email, "phone": "0771234567",
                                                    "password": PW, "role": role})
    r.raise_for_status()
    return r.json()


def api(method, path, token=None, **kw):
    h = {"Authorization": "Bearer " + token} if token else {}
    return requests.request(method, API + path, headers=h, **kw)


def outbox(kind=None, to=None):
    mails = requests.get(API + "/_test/emails").json()
    return [m for m in mails if (kind is None or m["kind"] == kind) and (to is None or m["to"] == to)]


def clear_outbox():
    requests.delete(API + "/_test/emails")


def login(pg, email, pw=PW):
    pg.evaluate("localStorage.clear()")
    pg.goto(U + "#/login", wait_until="networkidle"); pg.wait_for_timeout(900)
    pg.fill('input[type=email]', email)
    pg.fill('input[type=password]', pw)
    pg.click('button[type=submit]')
    pg.wait_for_timeout(2200)


def logout(pg):
    pg.evaluate("localStorage.clear()")
    pg.goto(U, wait_until="networkidle")
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(1500)


def tab(pg, label):
    pg.locator(".dash-side a", has_text=label).first.click()
    pg.wait_for_timeout(1400)


def side_links(pg):
    return [t.strip() for t in pg.locator(".dash-side a").all_inner_texts()]


def top_links(pg):
    return [t.strip() for t in pg.locator(".nav-links a").all_inner_texts()]


# ---------------------------------------------------------------------
# Accounts and a job, created through the API so the browser steps below
# stay on the features being tested.
# ---------------------------------------------------------------------
worker = api_register("Kamal Perera", "ui-cv-worker@test.lk", "worker")
worker2 = api_register("Saman Silva", "ui-cv-worker2@test.lk", "worker")
employer = api_register("Ruwan Builders", "ui-cv-employer@test.lk", "employer")
org = api_register("Lanka Estates", "ui-cv-org@test.lk", "organization")

job_id = api("POST", "/jobs", employer["token"], json={
    "title": "CV Screen Mason", "category": "Construction", "location": "Kandy", "district": "Kandy",
    "requiredSkills": "Masonry", "pay": 2800, "per": "day", "workersNeeded": 2}).json()["id"]

with sync_playwright() as pw_:
    b = pw_.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.on("response", lambda r: missing.append(r.url) if r.status == 404 else None)

    def on_dialog(d):
        dialogs.append(d.message)
        d.accept()

    pg.on("dialog", on_dialog)

    # =================================================================
    print("\nM. PLANS / PRICING LINKS BY ROLE")
    # =================================================================
    pg.goto(U, wait_until="networkidle"); pg.wait_for_timeout(2200)
    check("a visitor who is not signed in sees Pricing in the menu", "Pricing" in top_links(pg), top_links(pg))
    check("and in the footer", pg.locator(".site-footer a", has_text="Pricing").count() == 1)

    login(pg, "ui-cv-worker@test.lk")
    check("a worker's dashboard has no Plans link", "Plans" not in side_links(pg), side_links(pg))
    check("a worker's top menu has no Pricing link", "Pricing" not in top_links(pg), top_links(pg))
    check("the worker's other menu items are untouched",
          all(x in " ".join(side_links(pg)) for x in
              ["Overview", "Recommended", "My Applications", "Payments", "Reviews", "Reports",
               "Notifications", "My Profile", "Browse Jobs", "Logout"]), side_links(pg))
    pg.goto(U, wait_until="networkidle"); pg.wait_for_timeout(1500)
    check("the footer hides Pricing from a signed-in worker",
          pg.locator(".site-footer a", has_text="Pricing").count() == 0)
    pg.goto(U + "#/dashboard", wait_until="networkidle"); pg.wait_for_timeout(1200)
    pg.screenshot(path=OUT + "/27-worker-menu-no-plans.png")

    login(pg, "ui-cv-employer@test.lk")
    check("an employer's dashboard has the Plans link", "Plans" in side_links(pg), side_links(pg))
    check("an employer's top menu has Pricing", "Pricing" in top_links(pg), top_links(pg))
    pg.screenshot(path=OUT + "/28-employer-menu-plans.png")
    tab(pg, "Plans")
    check("the employer's Plans link opens the plans page",
          "pricing" in pg.evaluate("location.hash") and "STARTER" in pg.inner_text("body"),
          pg.evaluate("location.hash"))

    login(pg, "ui-cv-org@test.lk")
    check("an organization's dashboard has the Plans link", "Plans" in side_links(pg), side_links(pg))

    login(pg, "admin@dailywork.lk", "Admin@12345")
    pg.goto(U + "#/dashboard", wait_until="networkidle"); pg.wait_for_timeout(1500)
    check("an administrator's dashboard has no Plans link", "Plans" not in side_links(pg), side_links(pg))
    check("an administrator's top menu has no Pricing link", "Pricing" not in top_links(pg), top_links(pg))
    check("the administrator still has the Admin Panel link",
          any("Admin Panel" in x for x in side_links(pg)), side_links(pg))

    logout(pg)
    check("signing out brings Pricing back for visitors", "Pricing" in top_links(pg), top_links(pg))

    # =================================================================
    print("\nN. CV UPLOAD IN THE WORKER'S PROFILE")
    # =================================================================
    login(pg, "ui-cv-employer@test.lk")
    tab(pg, "My Profile")
    check("an employer's profile has no CV section", pg.locator("#cv-panel").count() == 0)

    login(pg, "ui-cv-worker@test.lk")
    tab(pg, "My Profile")
    panel = pg.locator("#cv-panel")
    check("the worker's profile has a My CV section", panel.count() == 1 and "My CV" in panel.inner_text())
    check("it starts empty, with an Upload button",
          "You have not uploaded a CV yet" in panel.inner_text()
          and panel.locator("button", has_text="Upload CV").count() == 1, panel.inner_text()[:80])
    check("it says who will be able to see the CV",
          "sent to that employer" in panel.inner_text() and "Nobody else can see it" in panel.inner_text())

    pg.set_input_files("#cv-file", TXT_FILE); pg.wait_for_timeout(700)
    check("choosing a file that is not a PDF or Word document is refused on the spot",
          "PDF or Word document" in panel.locator(".form-msg.error").inner_text(),
          panel.inner_text()[:90])
    pg.set_input_files("#cv-file", BIG_FILE); pg.wait_for_timeout(700)
    check("choosing a file over 2 MB is refused on the spot",
          "up to 2 MB" in panel.locator(".form-msg.error").inner_text())
    pg.set_input_files("#cv-file", FAKE_PDF); pg.wait_for_timeout(1500)
    check("a program renamed to .pdf gets past the browser but is refused by the server",
          "does not look like a real" in panel.locator(".form-msg.error").inner_text(),
          panel.inner_text()[:90])
    check("after three refusals there is still no CV on the profile",
          "You have not uploaded a CV yet" in panel.inner_text()
          and api("GET", "/profile", worker["token"]).json()["hasCv"] is False)

    # Profile edits typed but not yet saved must survive a CV upload.
    pg.fill("#p-skills", "Masonry, Tiling (not saved yet)")
    pg.set_input_files("#cv-file", CV_FILE); pg.wait_for_timeout(1800)
    check("a real PDF uploads", "Your CV has been uploaded." in panel.inner_text(), panel.inner_text()[:90])
    check("the file's name and size are shown",
          "Kamal Perera CV.pdf" in panel.inner_text() and "6 KB" in panel.inner_text(),
          [l for l in panel.inner_text().split("\n") if "KB" in l])
    check("Download, Replace and Remove are offered",
          all(panel.locator("button", has_text=t).count() == 1 for t in ["Download", "Replace", "Remove"]))
    check("unsaved profile edits are still in the form after the upload",
          pg.input_value("#p-skills") == "Masonry, Tiling (not saved yet)", pg.input_value("#p-skills"))
    panel.scroll_into_view_if_needed()
    pg.screenshot(path=OUT + "/29-worker-cv-uploaded.png")

    with pg.expect_download() as dl:
        panel.locator("button", has_text="Download").click()
    got = dl.value
    saved = os.path.join(WORK, "downloaded-own.pdf"); got.save_as(saved)
    check("Download gives back exactly the file that was uploaded",
          open(saved, "rb").read() == PDF_A and got.suggested_filename == "Kamal Perera CV.pdf",
          got.suggested_filename)

    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(1500)
    tab(pg, "My Profile")
    panel = pg.locator("#cv-panel")
    check("the CV is still there after reloading the page", "Kamal Perera CV.pdf" in panel.inner_text())

    with pg.expect_file_chooser() as fc:
        panel.locator("button", has_text="Replace").click()
    fc.value.set_files(CV_NEW); pg.wait_for_timeout(1800)
    check("Replace opens the file picker and swaps the CV",
          "Your CV has been replaced." in panel.inner_text() and "Kamal CV 2026.pdf" in panel.inner_text()
          and "Kamal Perera CV.pdf" not in panel.inner_text(), panel.inner_text()[:120])
    check("the new size is shown", "146 KB" in panel.inner_text() or "147 KB" in panel.inner_text(),
          [l for l in panel.inner_text().split("\n") if "KB" in l])
    check("the server holds the replacement",
          api("GET", "/profile/cv", worker["token"]).content == PDF_B)

    # =================================================================
    print("\nO. APPLYING SHARES THE CV WITH THAT EMPLOYER")
    # =================================================================
    check("before applying, the employer cannot fetch the CV",
          api("GET", f"/profile/{worker['id']}/cv", employer["token"]).status_code == 403)

    clear_outbox()
    pg.goto(U + "#/job?id=" + str(job_id), wait_until="networkidle"); pg.wait_for_timeout(1800)
    check("the apply form tells the worker their CV goes with the application",
          "it is sent to this employer with your application" in pg.inner_text("body"))
    pg.fill("#apply-note", "Twelve years of masonry.")
    pg.locator("button", has_text="Apply Now").first.click()
    pg.wait_for_timeout(2200)
    check("the application is sent", "application has been sent" in pg.inner_text("body").lower())

    api("POST", "/applications", worker2["token"], json={"jobId": job_id})      # applicant with no CV

    # ---- P (first part): the emails that applying produced ----
    conf = outbox("application_received", "ui-cv-worker@test.lk")
    check("applying through the site emails the worker a confirmation",
          len(conf) == 1 and conf[0]["subject"] == "Application sent: CV Screen Mason",
          [m["subject"] for m in conf])
    alert_ = outbox("new_applicant", "ui-cv-employer@test.lk")
    check("and emails the employer, with the CV attached",
          len(alert_) == 2 and
          any(m["attachments"] and m["attachments"][0]["fileName"] == "Kamal CV 2026.pdf"
              and m["attachments"][0]["size"] == len(PDF_B) for m in alert_),
          [(m["subject"], [a["fileName"] for a in m["attachments"]]) for m in alert_])

    login(pg, "ui-cv-employer@test.lk")
    tab(pg, "Applicants")
    row = pg.locator(".activity li", has_text="Kamal Perera").first
    row2 = pg.locator(".activity li", has_text="Saman Silva").first
    check("the employer sees a CV button on the applicant who has one",
          row.locator("button", has_text="CV").count() == 1)
    check("and no CV button on the applicant who has none",
          row2.locator("button", has_text="CV").count() == 0)
    pg.screenshot(path=OUT + "/30-applicant-cv-button.png")

    with pg.expect_download() as dl:
        row.locator("button", has_text="CV").click()
    got = dl.value
    saved = os.path.join(WORK, "downloaded-by-employer.pdf"); got.save_as(saved)
    check("the employer downloads the applicant's CV, unchanged",
          open(saved, "rb").read() == PDF_B and got.suggested_filename == "Kamal CV 2026.pdf",
          got.suggested_filename)

    # =================================================================
    print("\nP. EMAILS WHEN AN APPLICATION IS ACCEPTED AND WHEN A JOB IS POSTED")
    # =================================================================
    clear_outbox()
    row.locator("button", has_text="Hire").click()
    pg.wait_for_timeout(1800)
    check("the employer hires the applicant", "accepted" in pg.inner_text(".dash-main"))
    hired = outbox("application_accepted")
    check("hiring emails the worker that they were accepted",
          [(m["to"], m["subject"]) for m in hired]
          == [("ui-cv-worker@test.lk", "You have been hired: CV Screen Mason")],
          [(m["to"], m["subject"]) for m in outbox()])
    check("with the employer's contact details",
          hired and hired[0]["details"].get("Employer email") == "ui-cv-employer@test.lk")

    clear_outbox()
    row2.locator("button", has_text="Decline").click()
    pg.wait_for_timeout(1800)
    check("declining emails that applicant",
          [(m["to"], m["subject"]) for m in outbox()]
          == [("ui-cv-worker2@test.lk", "Update on your application: CV Screen Mason")],
          [(m["to"], m["subject"]) for m in outbox()])

    api("PUT", "/profile", worker2["token"], json={
        "name": "Saman Silva", "phone": "0771234567", "skills": "Painting", "location": "Galle",
        "district": "Galle", "available": True})
    clear_outbox()
    tab(pg, "Post a Job")
    pg.fill('input[placeholder="e.g. Construction Helper"]', "Email Test Painter")
    pg.select_option(".dash-panel select >> nth=0", "Construction")
    # Location on the job form is a dropdown (the second select, after Category).
    pg.select_option(".dash-panel select >> nth=1", "Galle")
    pg.fill('input[placeholder="2500"]', "2600")
    pg.fill("#j-skills", "Painting")
    pg.fill("#j-workers", "1")
    pg.click(".dash-panel button[type=submit]")
    pg.wait_for_timeout(2200)
    check("a job is posted through the form", "Job posted" in pg.inner_text(".dash-main"),
          pg.inner_text(".dash-main")[:120])
    posted = outbox("job_posted")
    check("posting emails the employer a confirmation",
          [(m["to"], m["subject"]) for m in posted]
          == [("ui-cv-employer@test.lk", "Your job is live: Email Test Painter")],
          [(m["to"], m["subject"]) for m in outbox()])
    check("and emails the worker whose profile matches the new job",
          "ui-cv-worker2@test.lk" in [m["to"] for m in outbox("job_match")],
          [m["to"] for m in outbox("job_match")])

    # =================================================================
    print("\nQ. EMAIL ME THIS REPORT")
    # =================================================================
    clear_outbox(); dialogs.clear()
    tab(pg, "Reports")
    btn = pg.locator("button", has_text="Email me this report")
    check("the employer's report has an Email me this report button", btn.count() == 1)
    check("the CSV export button is still there",
          pg.locator("button", has_text="Export payments (CSV)").count() == 1)
    pg.screenshot(path=OUT + "/31-employer-report-email-button.png")
    btn.click(); pg.wait_for_timeout(1800)
    check("clicking it reports what happened",
          len(dialogs) == 1 and "report" in dialogs[0].lower(), dialogs)
    er = outbox("report_employer")
    check("the hiring report is emailed to the employer's own address, with the CSV",
          len(er) == 1 and er[0]["to"] == "ui-cv-employer@test.lk"
          and [a["fileName"] for a in er[0]["attachments"]] == ["dailywork-employer-payments.csv"],
          [(m["to"], [a["fileName"] for a in m["attachments"]]) for m in outbox()])

    dialogs.clear()
    btn.click(); pg.wait_for_timeout(1500)
    check("a second click straight away is held back with a clear message",
          len(dialogs) == 1 and "wait" in dialogs[0].lower() and len(outbox("report_employer")) == 1, dialogs)

    login(pg, "ui-cv-worker@test.lk")
    clear_outbox(); dialogs.clear()
    tab(pg, "Reports")
    pg.locator("button", has_text="Email me this report").click(); pg.wait_for_timeout(1800)
    wr = outbox("report_worker")
    check("a worker can email themselves their work report",
          len(wr) == 1 and wr[0]["to"] == "ui-cv-worker@test.lk"
          and wr[0]["details"].get("Currently hired") == "1"
          and [a["fileName"] for a in wr[0]["attachments"]] == ["dailywork-payments.csv"],
          wr and wr[0]["details"])

    login(pg, "admin@dailywork.lk", "Admin@12345")
    pg.goto(U + "#/admin", wait_until="networkidle"); pg.wait_for_timeout(1500)
    tab(pg, "Reports")
    clear_outbox(); dialogs.clear()
    pg.locator("button", has_text="Email me this report").click(); pg.wait_for_timeout(1800)
    ar = outbox("report_admin")
    check("an administrator can email the platform report",
          len(ar) == 1 and [a["fileName"] for a in ar[0]["attachments"]] == ["dailywork-jobs.csv"],
          [(m["kind"], [a["fileName"] for a in m["attachments"]]) for m in outbox()])
    check("and is told it was saved, not sent, because the admin address is a demonstration one",
          len(dialogs) == 1 and "demonstration account" in dialogs[0], dialogs)

    # =================================================================
    print("\nR. REMOVING A CV")
    # =================================================================
    login(pg, "ui-cv-worker@test.lk")
    tab(pg, "My Profile")
    panel = pg.locator("#cv-panel")
    dialogs.clear()
    panel.locator("button", has_text="Remove").click(); pg.wait_for_timeout(1800)
    check("removing asks for confirmation first", len(dialogs) == 1 and "Remove your CV" in dialogs[0], dialogs)
    check("the CV is removed and the section goes back to empty",
          "Your CV has been removed." in panel.inner_text()
          and "You have not uploaded a CV yet" in panel.inner_text(), panel.inner_text()[:120])
    check("the employer can no longer download it",
          api("GET", f"/profile/{worker['id']}/cv", employer["token"]).status_code == 404)

    login(pg, "ui-cv-employer@test.lk")
    tab(pg, "Applicants")
    check("and the CV button is gone from the employer's applicants list",
          pg.locator(".activity li", has_text="Kamal Perera").first
            .locator("button", has_text="CV").count() == 0)

    # =================================================================
    print("\nS. PHONE-SIZED SCREEN")
    # =================================================================
    api("POST", "/profile/cv", worker["token"], files={"file": ("Kamal Perera CV.pdf", PDF_A, "application/pdf")})
    pg.set_viewport_size({"width": 390, "height": 844})
    login(pg, "ui-cv-worker@test.lk")
    tab(pg, "My Profile")
    pg.locator("#cv-panel").scroll_into_view_if_needed(); pg.wait_for_timeout(600)
    wide = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("the CV section fits a phone screen", wide <= 1, f"overflow={wide}px")
    pg.screenshot(path=OUT + "/32-mobile-cv.png")
    tab(pg, "Reports"); pg.wait_for_timeout(600)
    wide = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("the report buttons fit a phone screen", wide <= 1, f"overflow={wide}px")

    b.close()

# The 404s and console errors below are the ones the tests cause on purpose:
# the CV that was removed, and requests the server is meant to refuse.
expected = ("/cv", "/reports/email")
real_missing = [u for u in missing if not any(x in u for x in expected)]
real_errors = [e for e in errs if "Failed to load resource" not in e]

print()
print("  404s  :", real_missing or "none")
print("  errors:", real_errors or "none (only expected rejections)")
print()
if fails or real_missing or real_errors:
    print("RESULT: FAILURES ->", fails + real_missing + real_errors)
    sys.exit(1)
print("RESULT: ALL CV, PLANS-MENU AND EMAIL UI CHECKS PASSED")
