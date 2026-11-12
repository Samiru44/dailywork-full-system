# Database and Migration Instructions

**Your existing data is not deleted.** If you already have a
`backend/DailyWork.Api/dailywork.db` from the earlier version, keep it where it
is. The first start of the updated application upgrades it in place and leaves
every row intact. This was tested against real SQLite files with real rows in
them — 19 executed checks, see `TEST-RESULTS.md`.

Even so: **make a copy before you start.** It costs nothing.

```powershell
cd backend\DailyWork.Api
copy dailywork.db dailywork.db.backup
```

---

## What happens on first start

`Program.cs` calls `DatabaseBootstrapper.EnsureUpToDate(...)` before the server
accepts requests. It:

1. Creates the database from the current model if there is none.
2. Otherwise adds the **45 new columns** and **5 new tables** that the new
   features need, each guarded so an existing column is never added twice.
   Tables are created **before** columns are added, so a table created by this
   run already carries every column its definition declares. (The other way
   round, a newly created table would be missing any column added in a later
   release until the application was restarted a second time — and would be
   queried in between with those columns absent. The upgrade test caught exactly
   that.)
3. Converts the money columns from rupees to whole cents **once**, recording a
   marker row so it can never run a second time.
4. Back-fills sensible values: `AgreedRate` from the job's wage, `AmountPaid` for
   payments already marked paid, `UnitsWorked = 1` where no work records exist,
   and `ConfirmedAmount` for payments the worker had already confirmed under the
   old one-way flag — so nobody is asked to confirm the same money twice. Work
   records that already existed default to `approved`, because they were all
   entered by the employer, so no payment total changes.

It is safe to start the application any number of times. The second run reports
`0 changes`.

### New tables

| Table | Holds |
|---|---|
| `WorkRecords` | Each day or shift worked on an assignment |
| `PaymentAudits` | Append-only history of every payment change |
| `JobCategories` | Job categories, previously a hardcoded list |
| `ContactMessages` | Submissions from the public contact form |
| `Projects` | An organization's project, that several job postings belong to |
| `CvDocuments` | A worker's uploaded CV: file name, server-decided type, size, the file itself, upload time. One per worker (unique index on `UserId`); deleted with the account |

### New columns, by table

| Table | Columns added |
|---|---|
| `Users` (18) | `IsActive`, `DeactivatedAt`, `DeactivationReason`, `SecurityStamp`, `District`, `Experience`, `ExperienceYears`, `Certifications`, `VerificationStatus`, `OrganizationName`, `RegistrationNumber`, `OrganizationAddress`, `OrganizationWebsite`, `VerificationNotes`, `VerificationDecisionNote`, `VerificationRequestedAt`, `VerifiedAt`, `VerifiedByUserId` |
| `Jobs` (7) | `District`, `RequiredSkills`, `WorkersNeeded`, `ExpectedUnits`, `StartDate`, `EndDate`, `UpdatedAt` |
| `Applications` (5) | `Message`, `ShortlistedAt`, `AcceptedAt`, `RejectedAt`, `CompletedAt` |
| `Payments` (11) | `ApplicationId`, `AgreedRate`, `RateUnit`, `UnitsWorked`, `AmountPaid`, `Method`, `Notes`, `WorkerConfirmed`, `WorkerConfirmedAt`, `WorkerDisputeNote`, `ConfirmedAmount` |
| `WorkRecords` (3) | `Status`, `SubmittedByUserId`, `DecisionNote` |
| `Jobs` (+1) | `ProjectId` |

---

## Why money is stored as cents

The old schema stored wages and payment amounts as `REAL` (floating point).
Floating point cannot represent most decimal fractions exactly, so sums drift:
add a few payments and a worker's total earnings no longer equals the sum of what
was recorded. For a payment-tracking system that is not acceptable.

`AppDbContext.cs` now converts every money value to a whole number of cents on
the way into the database and divides on the way out:

```csharp
private static readonly ValueConverter<decimal, long> MoneyConverter = new(
    value  => (long)Math.Round(value * 100m, MidpointRounding.AwayFromZero),
    stored => stored / 100m);
```

Rs. 2,400.00 is stored as `240000`. Rs. 1,537.45 is stored as `153745`. Totals
are exact, and the values sort and sum correctly in SQL.

The upgrade multiplies the existing values by 100 once. Because the result is
always a whole number, it is represented exactly even in the old `REAL` column,
so no table rebuild is needed.

### The dangerous case, and the guard against it

An early version of the upgrader had a real defect: on a **brand-new** database
it returned early without recording the conversion marker, so the *next* start
would have multiplied every amount by 100 again. Rs. 2,500 would have become
Rs. 250,000.

The fix records the marker on the fresh-install path before returning, and the
test suite now covers exactly this:

```
PASS  fresh database is never rescaled              -> Pay=250000
PASS  marker recorded on fresh install
PASS  restart after fresh install leaves money alone -> Pay=250000
PASS  second run applies no changes                  -> 0 change(s)
PASS  money NOT multiplied a second time             -> Pay=320000.0
```

---

## Proper EF Core migrations — recommended, and over to you

`DatabaseBootstrapper.cs` exists because the machine this work was done on has
**no .NET SDK**, so `dotnet ef migrations add` could not be run and a hand-written
migration snapshot could not be compiled or checked. Writing one blind would have
been riskier than a plain SQL upgrader I could actually execute and test.

For your submission and for anything beyond it, generating real migrations on
your own machine is the better route. The bootstrapper and EF migrations coexist
safely: the bootstrapper only ever adds something that is missing, so once
migrations have created those columns it finds nothing to do and reports
`0 changes`.

### Generate the migrations

```powershell
# once per machine
dotnet tool install --global dotnet-ef

cd backend\DailyWork.Api

# with your existing database still in place
dotnet ef migrations add AuditPhaseSchema

# apply it
dotnet ef database update
```

`dotnet ef migrations add` compares the current model against the last snapshot,
so on a project with no previous migrations the first one contains the whole
schema. If `dotnet ef database update` then complains that a table already
exists, your database is already at the right shape (the bootstrapper got there
first) and you only need to mark the migration as applied:

```powershell
dotnet ef migrations add AuditPhaseSchema
dotnet ef database update 0 --no-build   # only on a database you can afford to reset
```

On a database with data you want to keep, leave the bootstrapper to do the
upgrade and keep the generated migration as documentation of the schema. Do not
run `dotnet ef database drop` — it deletes the file.

### Useful commands

| Command | What it does |
|---|---|
| `dotnet ef migrations list` | Shows which migrations exist and which are applied |
| `dotnet ef migrations script` | Prints the SQL instead of running it, so you can read it first |
| `dotnet ef dbcontext info` | Confirms which database file is in use |

---

## Starting over deliberately

Only if you *want* to lose the data — for a clean demonstration, say:

```powershell
cd backend\DailyWork.Api
del dailywork.db
dotnet run
```

A fresh database is created and seeded with the demonstration accounts and jobs.

---

## Inspecting the database

[DB Browser for SQLite](https://sqlitebrowser.org/) opens
`backend/DailyWork.Api/dailywork.db` directly. Remember that money columns hold
**cents** — divide by 100 to read them as rupees.

To confirm an upgrade went through:

```sql
SELECT * FROM SchemaUpgrades;        -- one row per applied upgrade step
                                     -- ('money-to-cents-v1', 'confirmed-amount-v1')
SELECT Id, Amount, AmountPaid, Status FROM Payments;
```
