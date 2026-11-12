# CV Upload, Role-Based Plans Menu, and Email

This round added three features. Each one is covered by executed tests:
78 API checks (areas 28–30) and 60 browser checks (sections M–S). The raw
output is in `docs/test-evidence/api.txt` and `docs/test-evidence/ui_cv_email.txt`.

---

## 1. CV upload (job seekers)

**Where:** Dashboard → **My Profile** → **My CV** panel (workers only).

A worker can **upload**, **download**, **replace** and **remove** one CV.

| Rule | Detail |
|---|---|
| File types | PDF, Word `.doc`, Word `.docx` |
| Size | up to 2 MB |
| Type check | done twice: by the extension **and** by the file's first bytes, so a program or web page renamed to `.pdf` is refused |
| Content type | decided by the server, never taken from the browser |
| File name | any folder path is stripped (`C:\Users\...\my cv.pdf` → `my cv.pdf`, `../../x.pdf` → `x.pdf`) |
| Storage | its own table, `CvDocuments` (one row per worker), so the file is only loaded when someone downloads it |

**Who can download a worker's CV:**

- the worker themselves
- an administrator
- an employer or organization **the worker has applied to**, and no other

Anyone else gets `403`. For them, the profile doesn't show that a CV exists.
Employers see a **CV** button on each applicant who has one.

**API**

| Method | Endpoint | Who | Purpose |
|---|---|---|---|
| POST | `/api/profile/cv` | worker | upload or replace; `multipart/form-data`, field name `file` |
| GET | `/api/profile/cv` | worker | download your own CV |
| DELETE | `/api/profile/cv` | worker | remove your CV |
| GET | `/api/profile/{id}/cv` | that worker, admin, or an employer they applied to | download a worker's CV |

`GET /api/profile` now also returns `hasCv`, `cvFileName`, `cvSizeBytes` and
`cvUploadedAt`. Each applicant in `GET /api/employer/applicants` carries
`workerHasCv` and `workerCvFileName`.

---

## 2. Plans / Pricing menu shown only to the right roles

Paid plans are for the hiring side, so the menu now follows the role:

| Who | Top-menu **Pricing** | Footer **Pricing** | Dashboard **Plans** |
|---|---|---|---|
| Visitor (not signed in) | shown | shown | — |
| Worker | hidden | hidden | hidden |
| Employer | shown | shown | shown |
| Organization | shown | shown | shown |
| Administrator | hidden | hidden | hidden |

One rule decides all three places, `canSeePlans(user)` in `frontend-src/app.jsx`,
so the menus can't disagree with each other.

---

## 3. Emails

### When emails are sent

| Event | Who gets it | What it contains |
|---|---|---|
| **Job posted** | the employer | confirmation that the job is live, with the exact wage |
| **Job posted** | each worker whose skills and district match | "new job that matches your profile" (the same workers who get the in-app alert) |
| **Applied** | the worker | confirmation, and whether their CV went with it |
| **Applied** | the employer | the applicant's details, **with the CV attached** when there is one |
| **Shortlisted** | the worker | status update (does not reveal the employer's contact details yet) |
| **Accepted / hired** | the worker | "you have been hired", with the employer's phone and email so work can be arranged |
| **Declined** | that worker only | status update |
| **Work verified** | the worker | confirmation that the work was verified |
| **Report** | the person who asked, at their own account address only | the report's headline figures, with a CSV attached |

Reports are sent from the **Email me this report** button on the Reports tab:

- workers get their work report
- employers and organizations get their hiring report
- administrators get the platform report

Each report can be sent once a minute. The platform report attaches the jobs
list but **not** the users list, because that list holds everyone's contact
details.

Nothing is emailed when a request is refused, for example a duplicate
application, a status change by the wrong employer, or a job that fails
validation.

### How sending works

Controllers only put the email on a queue (`EmailQueue`). A background service
(`EmailDispatcher`) sends it afterwards. So a slow or broken mail server can
never slow down a request, and never undoes the application, hiring or job
posting that triggered the email.

### Three delivery modes

| Mode | When | What happens |
|---|---|---|
| **Outbox** (the default) | no mail server configured | each email is saved as an `.eml` file in `backend/DailyWork.Api/email-outbox/`. Double-click one to open it in Outlook or Windows Mail and see exactly what would have been sent, attachments included. |
| **SMTP** | `Smtp:Host` and a From address are set | emails are really sent |
| **Off** | no mail server and `OutboxFolder` set to empty | emails are only noted in the server log |

**Demo accounts are never really emailed.** The seeded `@dailywork.lk`
addresses belong to nobody, so mail for them always goes to the outbox folder,
even after you connect a real mail server. To see real delivery, register a new
account with your own email address.

### Turning on real email (Gmail example)

1. In your Google account, turn on **2-Step Verification**, then create an
   **App Password** (Google Account → Security → App passwords). Use that
   16-character password. Your normal Gmail password will not work.
2. Set these environment variables in the terminal you start the server from
   (Command Prompt shown):

   ```bat
   set Smtp__Host=smtp.gmail.com
   set Smtp__Port=587
   set Smtp__Username=yourname@gmail.com
   set Smtp__Password=your-16-character-app-password
   set Smtp__From=yourname@gmail.com
   ```

   Note the **two** underscores. To make them permanent, use `setx` instead of
   `set` and open a new terminal.
3. Start the server as usual (`START-DAILYWORK.bat` or `dotnet run`).
4. Register a worker with your own email address and apply for a job. The
   confirmation should arrive within a few seconds.

Outlook/Hotmail works the same way with `smtp-mail.outlook.com`. SendGrid,
Brevo and Mailgun give you an SMTP host, user name and password to put in the
same variables.

**Keep the password out of `appsettings.json`.** That file is committed to Git.
Environment variables aren't.

### Where to look when an email doesn't arrive

- The server window logs every email it sends or saves, and any SMTP error.
- Check the recipient's spam folder.
- A Gmail "Username and Password not accepted" error means you used your normal
  password instead of an App Password.

---

## 4. Phone-layout fix (found while testing)

The phone-size browser test found a problem that **already existed** in the
version you sent: on phones, the signed-in header was wider than the screen.
At 360 px (the most common Android width), a worker got 53 px of sideways
scrolling and an administrator 170 px, which pushed the ☰ menu button off
the screen.

The fix is CSS only and applies only below 860 px wide; the desktop layout is
unchanged. On phones the header buttons are more compact, the dashboard columns
shrink to the screen, and an administrator's header shows the logo without the
name to make room for the third button. A sweep of every public page and every
dashboard tab, for all five roles at 320, 360 and 390 px, now finds **no
sideways scrolling** (`docs/test-evidence/phone_layout.txt`).
