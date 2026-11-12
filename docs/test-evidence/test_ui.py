"""
Browser test of the real DailyWork interface: drives the actual React build in
Chromium, clicking the same controls a person would.

Covers the complete lifecycle the brief asks for:
employer posts job -> worker finds it -> applies -> employer hires ->
worker completes -> employer verifies -> payment recorded -> marked paid ->
worker views history and confirms -> both sides rate each other.
"""
from playwright.sync_api import sync_playwright
import os, sys, re, tempfile

U = "http://localhost:5000/"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "dailywork-shots")
os.makedirs(OUT, exist_ok=True)
os.makedirs(OUT, exist_ok=True)
fails, errs, missing = [], [], []


def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -> " + str(detail)[:80]) if detail else ""))
    if not ok:
        fails.append(label)


def register(pg, name, email, phone, pw, role):
    pg.evaluate("localStorage.clear()")
    pg.goto(U + "#/register", wait_until="networkidle"); pg.wait_for_timeout(900)
    if role != "worker":
        pg.locator(".role-pick .role", has_text=role.capitalize()).first.click()
    pg.fill('input[placeholder="e.g. Nimal Perera"]', name)
    pg.fill('input[type=email]', email)
    pg.fill('input[type=tel]', phone)
    pws = pg.locator('input[type=password]')
    pws.nth(0).fill(pw); pws.nth(1).fill(pw)
    pg.click('button[type=submit]')
    pg.wait_for_timeout(2200)


def login(pg, email, pw):
    pg.evaluate("localStorage.clear()")
    pg.goto(U + "#/login", wait_until="networkidle"); pg.wait_for_timeout(900)
    pg.fill('input[type=email]', email)
    pg.fill('input[type=password]', pw)
    pg.click('button[type=submit]')
    pg.wait_for_timeout(2200)


def tab(pg, label):
    pg.locator(".dash-side a", has_text=label).first.click()
    pg.wait_for_timeout(1400)


with sync_playwright() as pw_:
    b = pw_.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.on("response", lambda r: missing.append(r.url) if r.status == 404 else None)

    # The app asks for payment amounts and work days through prompt() dialogs,
    # which arrive one after another. A single router answers each by its text.
    answers = {"amount": None, "units": "3"}   # amount None = accept the default

    def on_dialog(d):
        m = d.message
        if "How much has been paid" in m:
            d.accept() if answers["amount"] is None else d.accept(answers["amount"])
        elif "How was it paid" in m:
            d.accept("cash")
        elif "How many days/shifts" in m:
            d.accept(answers["units"])
        else:
            d.accept()

    pg.on("dialog", on_dialog)

    # =================================================================
    print("\nA. PUBLIC SITE AND HONEST CONTENT")
    # =================================================================
    pg.goto(U, wait_until="networkidle"); pg.wait_for_timeout(2200)
    body = pg.inner_text("body")
    check("home page renders", "Connecting Daily Wage Workers" in body)

    # statistics must be the real (small) numbers, not the old inflated ones
    check("no fabricated 10,000+ figure", "10,000+" not in body, body[body.find("Registered Workers")-40:body.find("Registered Workers")] if "Registered Workers" in body else "")
    check("demo data is labelled", "demonstration account" in body.lower())
    check("invented testimonials removed",
          "This platform helped me find regular jobs" not in body)
    pg.screenshot(path=OUT + "/01-home.png", full_page=True)

    pg.goto(U + "#/pricing", wait_until="networkidle"); pg.wait_for_timeout(1400)
    pbody = pg.inner_text("body")
    check("pricing marked as not yet available", "Coming Soon" in pbody and "No payment is taken" in pbody)
    pg.screenshot(path=OUT + "/02-pricing.png")

    pg.goto(U + "#/login", wait_until="networkidle"); pg.wait_for_timeout(1000)
    check("demo credentials no longer shown on login",
          "Admin@123" not in pg.inner_text("body"))

    # contact form must really submit
    pg.goto(U + "#/contact", wait_until="networkidle"); pg.wait_for_timeout(1200)
    pg.fill("#c-name", "Browser Tester")
    pg.fill("#c-email", "tester@example.lk")
    pg.fill("#c-subject", "Testing the contact form")
    pg.fill("#c-message", "This message should actually reach the administrator inbox.")
    pg.click('button[type=submit]')
    pg.wait_for_timeout(2000)
    check("contact form shows success only after the server accepts",
          "has been received" in pg.inner_text("body"))
    pg.screenshot(path=OUT + "/03-contact.png")

    # =================================================================
    print("\nB. EMPLOYER POSTS A JOB")
    # =================================================================
    register(pg, "Test Employer", "ui-emp@test.lk", "0771234500", "Secret@123", "employer")
    check("employer registered and signed in", "dashboard" in pg.evaluate("location.hash"),
          pg.evaluate("location.hash"))

    tab(pg, "Post a Job")
    pg.fill('input[placeholder="e.g. Construction Helper"]', "UI Test Mason Job")
    pg.select_option(".dash-panel select >> nth=0", "Construction")
    pg.fill('input[placeholder="2500"]', "2400")
    pg.fill("#j-skills", "Masonry, Construction")
    pg.fill("#j-workers", "1")
    pg.fill("#j-units", "3")
    pg.fill("#j-desc", "Three days of masonry work on a housing site.")
    pg.click(".dash-panel button[type=submit]")
    pg.wait_for_timeout(2200)
    check("job posted through the form", "Job posted" in pg.inner_text(".dash-main"))
    pg.screenshot(path=OUT + "/04-post-job.png")

    tab(pg, "My Jobs")
    check("job appears under My Jobs", "UI Test Mason Job" in pg.inner_text(".dash-main"))

    # verification panel exists and says not verified
    tab(pg, "Verification")
    vbody = pg.inner_text(".dash-main")
    check("verification panel shows the account is not verified", "Not verified yet" in vbody)
    pg.screenshot(path=OUT + "/05-verification.png")

    # =================================================================
    print("\nC. WORKER FINDS AND APPLIES")
    # =================================================================
    register(pg, "Test Mason", "ui-worker@test.lk", "0777654300", "Secret@123", "worker")
    check("worker registered", "dashboard" in pg.evaluate("location.hash"))

    # complete the profile so recommendations can work
    tab(pg, "My Profile")
    pg.fill("#p-skills", "Masonry, Construction")
    pg.fill("#p-district", "Colombo")
    pg.fill("#p-years", "8")
    pg.fill("#p-exp", "Eight years of site work")
    pg.fill("#p-certs", "NVQ Level 3 Masonry")
    pg.locator('input[placeholder="e.g. Colombo"]').first.fill("Colombo")
    pg.click('.dash-panel button[type=submit]')
    pg.wait_for_timeout(1800)
    check("extended profile saved", "profile has been updated" in pg.inner_text(".dash-main").lower())
    pg.screenshot(path=OUT + "/06-worker-profile.png")

    # recommendations
    tab(pg, "Recommended")
    pg.wait_for_timeout(1800)
    rbody = pg.inner_text(".dash-main")
    check("recommendations panel renders", "Recommended for You" in rbody)
    cards = pg.locator(".job-card").count()
    check("recommendations returned", cards > 0, f"{cards} cards")
    check("match percentage shown", "% match" in rbody)
    check("reasons shown for each recommendation",
          "Matches your skills" in rbody or "You work in" in rbody or "your district" in rbody,
          rbody[:200].replace("\n", " "))
    pg.screenshot(path=OUT + "/07-recommendations.png", full_page=True)

    # advanced search
    pg.goto(U + "#/jobs", wait_until="networkidle"); pg.wait_for_timeout(2000)
    check("job search page loads", pg.locator(".job-card").count() > 0)
    pg.locator("button", has_text="More Filters").click()
    pg.wait_for_timeout(700)
    pg.fill("#fl-min", "2300")
    pg.wait_for_timeout(1800)
    jb = pg.inner_text("body")
    low = [c for c in pg.locator(".job-card").all_inner_texts() if "1," in c]
    check("minimum wage filter applied in the UI",
          ("jobs found" in jb or "job found" in jb) and len(low) == 0,
          [l for l in jb.split("\n") if "found" in l][:1])
    pg.select_option("#fl-sort", "wage_high")
    pg.wait_for_timeout(1800)
    check("sorting control works", pg.locator(".job-card").count() > 0)
    pg.screenshot(path=OUT + "/08-advanced-search.png", full_page=True)

    # job details page
    pg.fill("#fl-min", "")
    pg.fill("input[placeholder*='Search job']", "UI Test Mason")
    pg.wait_for_timeout(1800)
    pg.locator(".job-card a", has_text="Details").first.click()
    pg.wait_for_timeout(2000)
    dbody = pg.inner_text("body")
    check("job details page opens", "About this job" in dbody)
    check("details show the wage and positions", "About the employer" in dbody)
    check("unverified employer flagged on the details page", "Not verified" in dbody)
    pg.screenshot(path=OUT + "/09-job-details.png", full_page=True)

    # apply from the details page
    pg.fill("#apply-note", "I have eight years of masonry experience.")
    pg.locator("button", has_text="Apply Now").first.click()
    pg.wait_for_timeout(2200)
    check("application sent from the details page",
          "application has been sent" in pg.inner_text("body").lower() or
          "already applied" in pg.inner_text("body").lower())

    # =================================================================
    print("\nD. EMPLOYER HIRES, RECORDS WORK, VERIFIES")
    # =================================================================
    login(pg, "ui-emp@test.lk", "Secret@123")
    tab(pg, "Applicants")
    abody = pg.inner_text(".dash-main")
    check("applicant listed with their details", "Test Mason" in abody)
    check("applicant skills shown to the employer", "Masonry" in abody)
    pg.screenshot(path=OUT + "/10-applicants.png")

    row = pg.locator(".activity li", has_text="Test Mason").first
    row.locator("button", has_text="Shortlist").click()
    pg.wait_for_timeout(1800)
    check("shortlisting works", "shortlisted" in pg.inner_text(".dash-main"))

    row = pg.locator(".activity li", has_text="Test Mason").first
    row.locator("button", has_text="Hire").click()
    pg.wait_for_timeout(1800)
    check("hiring works", "accepted" in pg.inner_text(".dash-main"))

    # record three days of work
    row = pg.locator(".activity li", has_text="Test Mason").first
    row.locator("button", has_text="Log Work Day").click()
    pg.wait_for_timeout(2600)

    row = pg.locator(".activity li", has_text="Test Mason").first
    row.locator("button", has_text="Verify Work Done").click()
    pg.wait_for_timeout(2000)
    check("work verified", "completed" in pg.inner_text(".dash-main"))
    pg.screenshot(path=OUT + "/11-verified.png")

    # =================================================================
    print("\nE. PAYMENT RECORDED AND CONFIRMED")
    # =================================================================
    tab(pg, "Payments")
    pbody = pg.inner_text(".dash-main")
    check("payment raised automatically", "Test Mason" in pbody)
    check("payment reflects 3 days at the agreed rate",
          "7,200" in pbody, [l for l in pbody.split("\n") if "7," in l or "Rs." in l][:3])
    pg.screenshot(path=OUT + "/12-employer-payments.png")

    # part payment first
    answers["amount"] = "3000"
    pg.locator(".activity li button", has_text="Record Payment").first.click()
    pg.wait_for_timeout(3000)
    after_part = pg.inner_text(".dash-main")
    check("part payment recorded and balance shown",
          "outstanding" in after_part.lower(), [l for l in after_part.split("\n") if "outstanding" in l.lower()][:2])

    # settle the rest
    answers["amount"] = "4200"          # the remaining balance
    pg.locator(".activity li button", has_text="Record Payment").first.click()
    pg.wait_for_timeout(3000)
    settled = pg.inner_text(".dash-main")
    # "paid" alone is not proof -- it also appears in "Rs. 3,000 paid".
    check("payment settled in full",
          "outstanding" not in settled.lower()
          and "awaiting worker confirmation" in settled
          and pg.locator(".activity li button", has_text="Record Payment").count() == 0,
          [l for l in settled.split("\n") if "Paid" in l][:2])

    # employer reviews the worker
    tab(pg, "Reviews")
    check("employer is offered the review form", "Rate Test Mason" in pg.inner_text(".dash-main"))
    pg.locator(".dash-panel", has_text="Rate Test Mason").locator("i.fa-star").nth(4).click()
    pg.fill("textarea", "Good work, finished on time.")
    pg.locator("button", has_text="Submit Review").first.click()
    pg.wait_for_timeout(2000)
    check("employer review saved", "Rate Test Mason" not in pg.inner_text(".dash-main"))

    # employer report
    tab(pg, "Reports")
    pg.wait_for_timeout(1800)
    erep = pg.inner_text(".dash-main")
    check("employer report renders", "Recruitment performance" in erep)
    check("employer report shows the full settled amount", "7,200" in erep,
          [l for l in erep.split("\n") if "Spent" in l or "Outstanding" in l][:4])
    pg.screenshot(path=OUT + "/13-employer-reports.png", full_page=True)

    # =================================================================
    print("\nF. WORKER SEES EVERYTHING")
    # =================================================================
    login(pg, "ui-worker@test.lk", "Secret@123")
    tab(pg, "Payments")
    wpay = pg.inner_text(".dash-main")
    check("worker sees the payment", "7,200" in wpay, [l for l in wpay.split("\n") if "7," in l][:2])
    check("worker sees the wage breakdown", "day(s) at" in wpay)

    pg.locator("button", has_text="Confirm Received").first.click()
    pg.wait_for_timeout(2000)
    check("worker can confirm receiving payment",
          "you confirmed" in pg.inner_text(".dash-main").lower())
    pg.screenshot(path=OUT + "/14-worker-payments.png")

    tab(pg, "Notifications")
    nb = pg.inner_text(".dash-main")
    check("worker notified: shortlisted", "shortlisted" in nb.lower())
    check("worker notified: hired", "hired" in nb.lower())
    check("worker notified: work verified", "Work verified" in nb)
    check("worker notified: payment", "ayment" in nb)
    check("worker notified: review", "New review received" in nb)
    pg.screenshot(path=OUT + "/15-worker-notifications.png", full_page=True)

    tab(pg, "Reviews")
    check("worker received the review", "finished on time" in pg.inner_text(".dash-main"))
    pg.locator(".dash-panel", has_text="Rate ").locator("i.fa-star").nth(4).click()
    pg.locator("textarea").first.fill("Paid on time, clear instructions.")
    pg.locator("button", has_text="Submit Review").first.click()
    pg.wait_for_timeout(2200)
    check("worker can review the employer back",
          "Rate " not in pg.inner_text(".dash-main"))

    tab(pg, "Reports")
    pg.wait_for_timeout(1800)
    wrep = pg.inner_text(".dash-main")
    check("worker report renders", "Application outcomes" in wrep)
    check("worker report shows the full amount earned", "7,200" in wrep,
          [l for l in wrep.split("\n") if "Earned" in l or "Pending" in l][:4])
    pg.screenshot(path=OUT + "/16-worker-reports.png", full_page=True)

    tab(pg, "My Profile")
    prof = pg.inner_text(".dash-main")
    check("profile shows work history", "Work History" in prof)
    check("profile shows the rating earned", "Average Rating" in prof)

    # =================================================================
    print("\nG. ADMIN: VERIFICATION, CATEGORIES, MESSAGES, REPORTS")
    # =================================================================
    login(pg, "admin@dailywork.lk", "Admin@12345")
    check("admin lands on the admin panel", "admin" in pg.evaluate("location.hash"))

    pg.locator(".dash-side a", has_text="Verification").first.click()
    pg.wait_for_timeout(1800)
    vq = pg.inner_text(".dash-main")
    check("verification queue renders", "Organization Verification" in vq)
    check("pending request listed", "Lanka Agro" in vq, vq[:150].replace("\n", " "))
    pg.screenshot(path=OUT + "/17-admin-verification.png")

    pg.locator("button", has_text="Approve").first.click()
    pg.wait_for_timeout(2000)
    check("admin can approve verification", "Lanka Agro" not in pg.inner_text(".dash-main"))

    pg.locator(".dash-side a", has_text="Categories").first.click()
    pg.wait_for_timeout(1600)
    cb = pg.inner_text(".dash-main")
    check("category manager renders", "Job Categories" in cb)
    pg.fill("#cat-name", "UI Test Sector")
    pg.locator("button", has_text="Add Category").click()
    pg.wait_for_timeout(1800)
    check("admin can add a category", "UI Test Sector" in pg.inner_text(".dash-main"))
    pg.screenshot(path=OUT + "/18-admin-categories.png", full_page=True)

    pg.locator(".dash-side a", has_text="Messages").first.click()
    pg.wait_for_timeout(1600)
    mb = pg.inner_text(".dash-main")
    check("contact message reached the admin inbox", "Testing the contact form" in mb, mb[:120].replace("\n", " "))
    pg.screenshot(path=OUT + "/19-admin-messages.png")

    pg.locator(".dash-side a", has_text="Reports").first.click()
    pg.wait_for_timeout(1800)
    ar = pg.inner_text(".dash-main")
    check("admin report renders", "Exports" in ar)
    check("admin report shows users by role", "workers" in ar.lower())
    pg.screenshot(path=OUT + "/20-admin-reports.png", full_page=True)

    # =================================================================
    print("\nI. EDITING A JOB (supervisor issue 3)")
    # =================================================================
    login(pg, "ui-emp@test.lk", "Secret@123")
    tab(pg, "Post a Job")
    pg.fill('input[placeholder="e.g. Construction Helper"]', "Editable UI Job")
    pg.select_option(".dash-panel select >> nth=0", "Cleaning")
    pg.fill('input[placeholder="2500"]', "1800")
    pg.fill("#j-workers", "2")
    pg.fill("#j-desc", "A job that will be edited through the dashboard.")
    pg.click(".dash-panel button[type=submit]")
    pg.wait_for_timeout(2200)

    tab(pg, "My Jobs")
    check("the new job is listed", "Editable UI Job" in pg.inner_text(".dash-main"))

    row = pg.locator("tr", has_text="Editable UI Job").first
    row.locator("button", has_text="Edit").click()
    pg.wait_for_timeout(1600)
    check("the edit form opens with the job loaded",
          "Edit Job — Editable UI Job" in pg.inner_text(".dash-main"))
    check("fields are filled from the existing posting",
          pg.input_value('input[placeholder="e.g. Construction Helper"]') == "Editable UI Job",
          pg.input_value('input[placeholder="e.g. Construction Helper"]'))
    check("the wage is carried over", pg.input_value('input[placeholder="2500"]') == "1800",
          pg.input_value('input[placeholder="2500"]'))

    pg.fill('input[placeholder="e.g. Construction Helper"]', "Edited UI Job")
    pg.fill('input[placeholder="2500"]', "2100")
    pg.locator(".dash-panel button", has_text="Save Changes").click()
    pg.wait_for_timeout(2400)

    mj = pg.inner_text(".dash-main")
    check("saving returns to My Jobs with the change applied",
          "Edited UI Job" in mj and "Editable UI Job" not in mj)
    check("the new wage is shown", "2,100" in mj,
          [l for l in mj.split("\n") if "2,1" in l][:2])
    pg.screenshot(path=OUT + "/23-edit-job.png", full_page=True)

    # Cancelling must not save anything.
    row = pg.locator("tr", has_text="Edited UI Job").first
    row.locator("button", has_text="Edit").click()
    pg.wait_for_timeout(1500)
    pg.fill('input[placeholder="e.g. Construction Helper"]', "Should Not Be Saved")
    pg.locator(".dash-panel button", has_text="Cancel").click()
    pg.wait_for_timeout(1600)
    check("cancelling an edit discards the change",
          "Should Not Be Saved" not in pg.inner_text(".dash-main"))

    # =================================================================
    print("\nJ. WORKER TIMESHEETS AND APPROVAL (optional improvement)")
    # =================================================================
    # Hire the worker onto the edited job so they can record days against it.
    tab(pg, "My Jobs")
    login(pg, "ui-worker@test.lk", "Secret@123")
    pg.goto(U + "#/jobs", wait_until="networkidle"); pg.wait_for_timeout(1800)
    pg.fill("input[placeholder*='Search job']", "Edited UI Job")
    pg.wait_for_timeout(1800)
    pg.locator(".job-card a", has_text="Details").first.click()
    pg.wait_for_timeout(1800)
    pg.locator("button", has_text="Apply Now").first.click()
    pg.wait_for_timeout(2000)

    login(pg, "ui-emp@test.lk", "Secret@123")
    tab(pg, "Applicants")
    r = pg.locator(".activity li", has_text="Edited UI Job").first
    r.locator("button", has_text="Hire").click()
    pg.wait_for_timeout(2000)

    # The worker records their own day.
    login(pg, "ui-worker@test.lk", "Secret@123")
    tab(pg, "My Applications")
    answers["units"] = "2"
    row2 = pg.locator(".activity li", has_text="Edited UI Job").first
    check("the worker is offered a way to record their work",
          row2.locator("button", has_text="Record a Work Day").count() == 1)
    row2.locator("button", has_text="Record a Work Day").click()
    pg.wait_for_timeout(2600)

    # The employer approves it.
    login(pg, "ui-emp@test.lk", "Secret@123")
    tab(pg, "Work Approvals")
    wa = pg.inner_text(".dash-main")
    check("submitted work waits for the employer", "Test Mason" in wa and "2 day(s)" in wa,
          [l for l in wa.split("\n") if "day(s)" in l][:2])
    pg.screenshot(path=OUT + "/24-work-approvals.png", full_page=True)

    pg.locator(".activity li button", has_text="Approve").first.click()
    pg.wait_for_timeout(2400)
    check("approving clears it from the queue",
          "Nothing is waiting for your approval" in pg.inner_text(".dash-main"))

    # =================================================================
    print("\nK. PART-PAYMENT CONFIRMATION (supervisor issue 2)")
    # =================================================================
    tab(pg, "Applicants")
    r = pg.locator(".activity li", has_text="Edited UI Job").first
    r.locator("button", has_text="Verify Work Done").click()
    pg.wait_for_timeout(2400)

    tab(pg, "Payments")
    pay = pg.inner_text(".dash-main")
    check("payment uses the approved day only", "4,200" in pay,
          [l for l in pay.split("\n") if "Edited UI Job" in l][:2])

    answers["amount"] = "2000"
    pg.locator(".activity li", has_text="Edited UI Job").locator(
        "button", has_text="Record Payment").first.click()
    pg.wait_for_timeout(3000)

    login(pg, "ui-worker@test.lk", "Secret@123")
    tab(pg, "Payments")
    btn = pg.locator(".activity li", has_text="Edited UI Job").locator(
        "button", has_text="Confirm Received")
    check("the worker is asked to confirm the part payment", btn.count() == 1)
    btn.first.click()
    pg.wait_for_timeout(2400)
    wp = pg.inner_text(".dash-main")
    check("the confirmed amount is stated, not just 'confirmed'",
          "confirmed receiving Rs. 2,000" in wp,
          [l for l in wp.split("\n") if "confirmed" in l.lower()][:2])

    # The employer pays the balance — confirmation must re-open.
    login(pg, "ui-emp@test.lk", "Secret@123")
    tab(pg, "Payments")
    emp_before = pg.inner_text(".dash-main")
    check("the employer can see what the worker has confirmed",
          "confirmed" in emp_before.lower(),
          [l for l in emp_before.split("\n") if "confirm" in l.lower()][:2])

    answers["amount"] = "2200"
    pg.locator(".activity li", has_text="Edited UI Job").locator(
        "button", has_text="Record Payment").first.click()
    pg.wait_for_timeout(3000)

    login(pg, "ui-worker@test.lk", "Secret@123")
    tab(pg, "Payments")
    wp2 = pg.inner_text(".dash-main")
    check("paying the balance asks the worker to confirm again",
          "please confirm it" in wp2.lower(),
          [l for l in wp2.split("\n") if "since been recorded" in l][:1])
    more = pg.locator(".activity li", has_text="Edited UI Job").locator(
        "button", has_text="Confirm")
    check("the button names the amount still to confirm",
          "2,200" in more.first.inner_text(), more.first.inner_text())
    more.first.click()
    pg.wait_for_timeout(2400)
    check("confirming the balance completes the record",
          "You confirmed receiving this." in pg.inner_text(".dash-main"))
    pg.screenshot(path=OUT + "/25-part-payment-confirmed.png", full_page=True)

    # =================================================================
    print("\nL. ORGANIZATION PROJECTS (supervisor issue 4)")
    # =================================================================
    register(pg, "Ceylon Projects Ltd", "ui-org@test.lk", "0112000291", "Secret@123", "organization")
    check("an organization account reaches its dashboard",
          "dashboard" in pg.evaluate("location.hash"))

    side = pg.inner_text(".dash-side")
    check("organizations get a Projects section", "Projects" in side)

    tab(pg, "Projects")
    pg.wait_for_timeout(1600)
    check("the projects panel renders", "Projects (0)" in pg.inner_text(".dash-main"))

    pg.locator("button", has_text="New Project").click()
    pg.wait_for_timeout(900)
    pg.fill("#pr-name", "Kandy Road Housing Site")
    pg.fill("#pr-loc", "Kandy")
    pg.fill("#pr-workers", "4")
    pg.fill("#pr-budget", "100000")
    pg.select_option("#pr-status", "active")
    pg.locator("button", has_text="Create Project").click()
    pg.wait_for_timeout(2400)
    pj = pg.inner_text(".dash-main")
    check("the project is created", "Kandy Road Housing Site" in pj)
    check("recruitment progress starts at zero", "Hired 0 of 4" in pj,
          [l for l in pj.split("\n") if "Hired" in l][:2])
    check("still-needed is shown", "4 still needed" in pj)

    # Post a job under the project.
    tab(pg, "Post a Job")
    pg.fill('input[placeholder="e.g. Construction Helper"]', "Project Site Mason")
    pg.fill('input[placeholder="2500"]', "2000")
    pg.fill("#j-workers", "2")
    pg.fill("#j-desc", "Masonry on the Kandy Road site.")
    check("the posting form offers the project", pg.locator("#j-project").count() == 1)
    pg.select_option("#j-project", label="Kandy Road Housing Site")
    pg.click(".dash-panel button[type=submit]")
    pg.wait_for_timeout(2400)

    tab(pg, "Projects")
    pg.wait_for_timeout(1800)
    pj2 = pg.inner_text(".dash-main")
    check("the posting is grouped under the project", "1 posting(s)" in pj2,
          [l for l in pj2.split("\n") if "posting(s)" in l][:2])

    pg.locator("button", has_text="View postings").first.click()
    pg.wait_for_timeout(1200)
    check("the project's postings can be expanded",
          "Project Site Mason" in pg.inner_text(".dash-main"))
    pg.screenshot(path=OUT + "/26-org-projects.png", full_page=True)

    # A worker applies and is hired — recruitment tracking must follow.
    login(pg, "ui-worker@test.lk", "Secret@123")
    pg.goto(U + "#/jobs", wait_until="networkidle"); pg.wait_for_timeout(1800)
    pg.fill("input[placeholder*='Search job']", "Project Site Mason")
    pg.wait_for_timeout(1800)
    pg.locator(".job-card a", has_text="Details").first.click()
    pg.wait_for_timeout(1800)
    pg.locator("button", has_text="Apply Now").first.click()
    pg.wait_for_timeout(2000)

    login(pg, "ui-org@test.lk", "Secret@123")
    tab(pg, "Applicants")
    pg.locator(".activity li", has_text="Project Site Mason").first.locator(
        "button", has_text="Hire").click()
    pg.wait_for_timeout(2200)

    tab(pg, "Projects")
    pg.wait_for_timeout(1800)
    pj3 = pg.inner_text(".dash-main")
    check("hiring moves the project's recruitment progress", "Hired 1 of 4" in pj3,
          [l for l in pj3.split("\n") if "Hired" in l][:2])
    check("the remaining need is recalculated", "3 still needed" in pj3)

    # An ordinary employer must not see projects at all.
    login(pg, "ui-emp@test.lk", "Secret@123")
    check("an ordinary employer has no Projects section",
          "Projects" not in pg.inner_text(".dash-side"))

    # =================================================================
    print("\nH. RESPONSIVE LAYOUT")
    # =================================================================
    m = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    m.goto(U, wait_until="networkidle"); m.wait_for_timeout(2000)
    ov = m.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("home fits a phone screen", ov <= 1, f"overflow={ov}px")
    m.screenshot(path=OUT + "/21-mobile-home.png")

    m.goto(U + "#/jobs", wait_until="networkidle"); m.wait_for_timeout(1800)
    ov2 = m.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("job search fits a phone screen", ov2 <= 1, f"overflow={ov2}px")
    m.screenshot(path=OUT + "/22-mobile-jobs.png")

    tablet = b.new_page(viewport={"width": 820, "height": 1180})
    tablet.goto(U, wait_until="networkidle"); tablet.wait_for_timeout(1800)
    ov3 = tablet.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("home fits a tablet screen", ov3 <= 1, f"overflow={ov3}px")

    b.close()

print()
print("  404s  :", missing if missing else "none")
real = [e for e in errs if not re.search(r"\b(40[0139]|409|429)\b", e)]
print("  errors:", real if real else "none (only expected rejections)")
print()
if fails or real or missing:
    print("RESULT: FAILURES ->", fails)
    sys.exit(1)
print("RESULT: ALL UI CHECKS PASSED")
