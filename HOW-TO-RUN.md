# How to Run DailyWork (Full System)

The backend serves the website as well, so there is **one thing to start and one
address to open**. No separate frontend server, no npm, no CORS setup.

---

## Step 1 — Install .NET 10 (one time only)

Download the **.NET 10.0 SDK** (not the Runtime):
**https://dotnet.microsoft.com/download/dotnet/10.0**

Install with the default options, then **close and reopen** any Command Prompt or
terminal window. Check it worked:

```
dotnet --version
```

You should see `10.0.xxx`. If you have an older SDK, install the .NET 10 SDK; it can be installed side by side with older versions.

> No database to install. The project uses SQLite, which is a single file created
> automatically on first run.

---

## Step 1b — If you already have a database from the earlier version

**Your data is kept.** Leave `backend/DailyWork.Api/dailywork.db` where it is;
the first start of this version upgrades it in place without losing any rows.
Make a copy first anyway:

```
cd backend\DailyWork.Api
copy dailywork.db dailywork.db.backup
```

See `docs/DATABASE.md` for exactly what the upgrade changes.

---

## Step 1c — Check it compiles (do this first)

```
cd path\to\DailyWork-FullSystem
dotnet build
```

Expect `Build succeeded`. **This step was not possible on the machine the code
was written on** (no .NET SDK was available there), so it is the first thing to
verify — see `docs/TEST-RESULTS.md`. If anything fails, the error names the file
and line.

---

## Step 2 — Start the system

**Windows:** double-click **`START-DAILYWORK.bat`**

**Mac / Linux:** run `./start-dailywork.sh`

**Any system, manually:**
```
cd backend/DailyWork.Api
dotnet run
```

The first run restores NuGet packages (needs internet, takes about a minute) and
creates the database. Wait until you see:

```
  Website:  http://localhost:5000
```

**Keep this window open.** Closing it stops the system.

---

## Step 3 — Open the site

Open your browser at:

## **http://localhost:5000**

That is the whole application. The API documentation (Swagger) is at
**http://localhost:5000/swagger** if you want to try the endpoints directly.

---

## Login accounts

| Role       | Email                      | Password       | Opens       |
|------------|----------------------------|----------------|-------------|
| **Admin**  | admin@dailywork.lk         | `Admin@12345`  | Admin Panel |
| **Worker** | worker@dailywork.lk        | `Password@123` | Dashboard   |
| Employer   | employer@dailywork.lk      | `Password@123` | Dashboard   |
| Organization | organization@dailywork.lk | `Password@123` | Dashboard  |

**These are no longer printed on the login page.** They are demonstration
accounts for a fresh install, and they are documented here rather than displayed
to every visitor.

**Change the administrator password after your first sign-in.** It is published
in these instructions, so it is not a secret.

You can also register a new Worker, Employer or Organization from the Register
page. New passwords must be at least 8 characters with a letter and a digit.

### Two things to know about a fresh install

- The homepage counts are read straight from the database. Because a fresh
  install ships with demonstration accounts, the homepage prints a note saying
  how many of the counted accounts are samples. Once you delete them, the note
  disappears by itself.
- The organization **Lanka Agro Services** is seeded with a *pending*
  verification request, so you can try the approval flow in
  Admin Panel → Verification straight away.

---

## Brevo email delivery (alternative to Gmail)

Brevo is supported by the same SMTP dispatcher already used by DailyWork.
You do not need to change the email templates, queue, controllers or report
attachments to switch providers.

1. Create or sign in to a Brevo account at <https://www.brevo.com/>.
2. In Brevo, configure a sender under **Settings → Senders, Domains & Dedicated
   IPs** and complete its verification. For reliable production delivery,
   authenticate a domain you own and add the SPF/DKIM DNS records Brevo provides.
3. Open **Settings → SMTP & API → SMTP**. Generate an SMTP key and copy it
   immediately. Use the SMTP login shown on that page; it may be different from
   your Brevo account login email.
4. In the extracted project folder, double-click
   **`START-DAILYWORK-BREVO.bat`**.
5. Enter the Brevo SMTP login, your verified sender email address, and the SMTP
   key when prompted. The key input is hidden and the credentials are only set
   for the running process; they are not saved in project files.
6. Confirm the startup line:
   `Email: sending through smtp-relay.brevo.com as your-verified-sender@example.com`

The launcher uses `smtp-relay.brevo.com`, port `587`, and STARTTLS. Use the
Brevo **SMTP key**, not the Brevo account password and not an API key.
Brevo documents port 2525 as an alternative if port 587 is blocked; the launcher
uses the recommended port 587 by default.

Official instructions:
- <https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP>
- <https://help.brevo.com/hc/en-us/articles/7959631848850-Create-and-manage-your-SMTP-keys>

### Test Brevo delivery

Use a newly registered DailyWork account with a real mailbox, not the seeded
`@dailywork.lk` demo accounts. Trigger a job posting or application notification,
or use **Reports → Email me this report**. Check Inbox and Spam/Junk, and check
the Brevo transactional logs if a message is not delivered. The server terminal
shows `Email sent: ...` on successful SMTP handoff and logs SMTP exceptions on
failure. SMTP acceptance confirms Brevo accepted the message; it does not
guarantee the recipient's inbox placement.

## Gmail email delivery (recommended)

The project supports real SMTP delivery. To use Gmail, you need a Gmail
**App Password**; your normal Google account password will not work.

1. Sign in to the Gmail account that will send DailyWork notifications.
2. Enable **2-Step Verification** in
   <https://myaccount.google.com/security>.
3. Create an App Password at
   <https://myaccount.google.com/apppasswords>. Google may require you to sign
   in again. Copy the 16-character password.
4. In the extracted project folder, double-click
   **`START-DAILYWORK-GMAIL.bat`**.
5. Enter the sender Gmail address and paste the App Password when prompted.
   Password input is hidden. The launcher keeps the SMTP password only in the
   current process environment; it does not write it to `appsettings.json` or
   save it permanently.
6. Wait for the startup line:
   `Email: sending through smtp.gmail.com as yourname@gmail.com`

Keep that terminal window open while using DailyWork. Closing it stops the
server and email dispatcher.

The launcher configures Gmail SMTP using `smtp.gmail.com`, port `587`, and
STARTTLS (`EnableSsl=true`). The From address is set to the authenticated Gmail
account. The SMTP password is never printed in the startup log.

### Test real delivery

- Do not use the seeded demo accounts for delivery. Their `@dailywork.lk`
  addresses are demonstration addresses, not real mailboxes, and are
  deliberately routed to `backend\\DailyWork.Api\\email-outbox\\` instead.
- Register a new worker or employer using an email address you can access.
- Trigger a real workflow, such as posting a job or applying for one, or use
  **Reports → Email me this report**.
- Check Inbox and Spam/Junk. The server terminal logs successful sends as
  `Email sent: ...` and failures with the SMTP exception details.
- If Gmail rejects authentication, create a new App Password and make sure
  2-Step Verification is enabled. Do not use your normal Gmail password.

If you prefer not to use the interactive launcher, set these environment
variables before starting the server: `Smtp__Host=smtp.gmail.com`,
`Smtp__Port=587`, `Smtp__Username`, `Smtp__Password`, `Smtp__EnableSsl=true`,
and `Smtp__From` (the same Gmail address). Keep the password out of source
control and `appsettings.json`.

Without SMTP credentials, the existing outbox mode remains available. Emails
are saved as `.eml` files in `backend\\DailyWork.Api\\email-outbox\\` and
can be opened with Outlook or Windows Mail.

---

## Checking that it all works

Once the site opens, run the end-to-end test against your own running backend.
This is the evidence your supervisor asked for.

```powershell
# leave `dotnet run` going in its own terminal, then from the project root:
pip install requests
python docs\test-evidence\test_real_backend.py
```

It runs the complete process as 112 checks — registration, job posting,
recommendation, application, hiring, work records, completion, payment, worker
confirmation and ratings, plus admin functions, organization approval, projects,
notifications and reports — and prints a PASS/FAIL summary you can paste into
your report.

It tags everything it creates with a unique run id and **deletes nothing**, so it
is safe to run against your own database, as often as you like.

If the administrator password has been changed from the seeded one:

```powershell
set DW_ADMIN_PASSWORD=your-password
```

---

## Troubleshooting

### "An Application Control policy has blocked this file"

```
Unable to start program 'C:\...\bin\Debug\net10.0\DailyWork.Api.exe'.
An Application Control policy has blocked this file.
```

**Your code is fine — it compiled.** Windows is refusing to *run* the program,
not failing to build it. The .NET SDK normally produces a small unsigned
launcher called `DailyWork.Api.exe`, and Windows security policy blocks unsigned
executables.

**This is already fixed in the project.** `DailyWork.Api.csproj` now sets
`<UseAppHost>false</UseAppHost>`, so no `.exe` is produced at all. The
application is started by `dotnet.exe` instead, which is signed by Microsoft and
is already trusted. Press F5 and it runs.

If you are looking at an older copy, or it still happens:

1. **Delete the stale `.exe` and rebuild.** The blocked file may be left over
   from a build made before the fix.
   ```powershell
   cd backend\DailyWork.Api
   dotnet clean
   dotnet build
   ```
2. **Start it without Visual Studio.** This always goes through `dotnet.exe`:
   ```powershell
   cd backend\DailyWork.Api
   dotnet run
   ```
   or run the compiled DLL directly:
   ```powershell
   dotnet bin\Debug\net10.0\DailyWork.Api.dll
   ```
3. **Unblock the extracted files.** Windows marks everything that came out of a
   downloaded ZIP as untrusted, which can trigger the same block. From the
   project folder:
   ```powershell
   Get-ChildItem -Recurse -File | Unblock-File
   ```
   (`START-DAILYWORK.bat` now does this for you.)
4. **Move the project off the Desktop or out of Documents**, to something like
   `C:\dev\DailyWork`. Some policies and Controlled Folder Access rules are
   path-based, and a path with spaces in it — `FINAL PROJECT` — occasionally
   upsets tooling too.

If it *still* happens, the block is coming from **Smart App Control** or a policy
your university or workplace manages:

- Check: **Windows Security → App & browser control → Smart App Control**.
- If it says **On**, it is blocking unsigned apps. Be aware before you change it:
  **Smart App Control can only be turned off, never back on** — switching it on
  again needs a Windows reinstall. You do not need to turn it off to run this
  project; use `dotnet run` instead, which the policy allows.
- On a laptop managed by the university, the policy is set by IT and cannot be
  changed locally. `dotnet run` is the way round it. For your demonstration, you
  can also run it from a personal machine.

### Everything else

| Problem | What to do |
|---|---|
| `'dotnet' is not recognized` | The .NET 10 SDK is not installed, or the terminal was open before installing. Install it, then open a **new** terminal. |
| `The framework 'Microsoft.NETCore.App', version '10.0.0' was not found` | The .NET 10 runtime is missing. Install the .NET 10.0 SDK from the link in Step 1. |
| `Address already in use` / port 5000 busy | Another program is using port 5000. Close it, or change the port in **both** `Program.cs` (`UseUrls`) and nothing else — the website uses a relative `/api` path, so it follows automatically. |
| Page loads but the job list is empty | The API is not responding. Look at the terminal window for a red error message. |
| Package restore fails | You need an internet connection for the first `dotnet run` only. After that it works offline. |
| Want to reset all data | Stop the server, delete `backend/DailyWork.Api/dailywork.db`, start again. It recreates and re-seeds itself. |

---

## Opening in an IDE

- **Visual Studio 2022** — open `DailyWork.sln`, press **F5**.
- **VS Code** — open the `DailyWork-FullSystem` folder, then run `dotnet run`
  from the terminal inside `backend/DailyWork.Api`.

---

## Switching from SQLite to SQL Server

SQLite needs no installation, which is why it is the default. To use SQL Server:

1. `dotnet add package Microsoft.EntityFrameworkCore.SqlServer`
2. In `Program.cs` change `opt.UseSqlite(...)` to `opt.UseSqlServer(...)`
3. In `appsettings.json` change the connection string, for example:
   `"Default": "Server=localhost;Database=DailyWork;Trusted_Connection=True;TrustServerCertificate=True"`

Nothing else changes — the models, controllers and website stay the same.
