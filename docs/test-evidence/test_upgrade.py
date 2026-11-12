"""
Verifies DatabaseBootstrapper's upgrade logic against a replica of the OLD
schema, using the exact SQL statements the C# file issues.

The point is to prove that an existing dailywork.db keeps all of its data and
that money values end up correct — and that running the upgrade twice does not
corrupt anything.
"""
import sqlite3, re, pathlib, sys, os

BOOT = pathlib.Path(sys.argv[1]).read_text()
import tempfile
DB = os.path.join(tempfile.gettempdir(), "dailywork-upgrade-test.db")
if os.path.exists(DB):
    os.remove(DB)

fails = []
def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -> " + detail) if detail else ""))
    if not ok:
        fails.append(label)

# ---------------------------------------------------------------
# Parse the column and table definitions straight out of the C# file,
# so this test exercises the real statements rather than a copy.
# ---------------------------------------------------------------
cols_block = BOOT.split("NewColumns =")[1].split("};")[0]
NEW_COLUMNS = re.findall(r'\("(\w+)",\s*"(\w+)",\s*"([^"]+)"\)', cols_block)

tables_block = BOOT.split("NewTables =")[1].split("\n    };")[0]
NEW_TABLES = re.findall(r'\("(\w+)",\s*"""\s*(CREATE TABLE.*?)\s*"""\)', tables_block, re.S)

print(f"parsed {len(NEW_COLUMNS)} column additions, {len(NEW_TABLES)} table additions\n")

# ---------------------------------------------------------------
# Build a database matching the PREVIOUS released schema
# ---------------------------------------------------------------
db = sqlite3.connect(DB)
db.executescript("""
CREATE TABLE "Users" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "Name" TEXT NOT NULL, "Email" TEXT NOT NULL, "Phone" TEXT NOT NULL,
  "PasswordHash" TEXT NOT NULL, "Role" TEXT NOT NULL, "CreatedAt" TEXT NOT NULL,
  "Skills" TEXT NOT NULL DEFAULT '', "Location" TEXT NOT NULL DEFAULT '',
  "Bio" TEXT NOT NULL DEFAULT '', "Available" INTEGER NOT NULL DEFAULT 1);
CREATE TABLE "Jobs" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "Title" TEXT NOT NULL, "Category" TEXT NOT NULL, "Location" TEXT NOT NULL,
  "Description" TEXT NOT NULL, "Pay" REAL NOT NULL, "Per" TEXT NOT NULL,
  "Urgent" INTEGER NOT NULL, "Status" TEXT NOT NULL, "CreatedAt" TEXT NOT NULL,
  "EmployerId" INTEGER NOT NULL);
CREATE TABLE "Applications" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "JobId" INTEGER NOT NULL, "WorkerId" INTEGER NOT NULL,
  "Status" TEXT NOT NULL, "CreatedAt" TEXT NOT NULL);
CREATE TABLE "Payments" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "JobId" INTEGER NOT NULL, "WorkerId" INTEGER NOT NULL,
  "Amount" REAL NOT NULL, "Status" TEXT NOT NULL,
  "PaidAt" TEXT NULL, "CreatedAt" TEXT NOT NULL);
CREATE TABLE "Ratings" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "JobId" INTEGER NOT NULL, "AuthorId" INTEGER NOT NULL, "SubjectId" INTEGER NOT NULL,
  "Stars" INTEGER NOT NULL, "Comment" TEXT NOT NULL, "SubjectRole" TEXT NOT NULL,
  "CreatedAt" TEXT NOT NULL);
CREATE TABLE "Notifications" (
  "Id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  "UserId" INTEGER NOT NULL, "Title" TEXT NOT NULL, "Message" TEXT NOT NULL,
  "Type" TEXT NOT NULL, "IsRead" INTEGER NOT NULL, "CreatedAt" TEXT NOT NULL);
""")

db.execute("INSERT INTO Users (Name,Email,Phone,PasswordHash,Role,CreatedAt) "
           "VALUES ('Nimal Perera','worker@x.lk','077','$2a$hash','worker','2026-01-01')")
db.execute("INSERT INTO Users (Name,Email,Phone,PasswordHash,Role,CreatedAt) "
           "VALUES ('Kasun','emp@x.lk','071','$2a$hash','employer','2026-01-01')")
db.execute("INSERT INTO Jobs (Title,Category,Location,Description,Pay,Per,Urgent,Status,CreatedAt,EmployerId) "
           "VALUES ('Mason','Construction','Kandy',' ',3200.0,'day',0,'open','2026-01-02',2)")
db.execute("INSERT INTO Jobs (Title,Category,Location,Description,Pay,Per,Urgent,Status,CreatedAt,EmployerId) "
           "VALUES ('Cleaner','Cleaning','Colombo',' ',1537.45,'day',0,'open','2026-01-02',2)")
db.execute("INSERT INTO Applications (JobId,WorkerId,Status,CreatedAt) VALUES (1,1,'completed','2026-01-03')")
db.execute("INSERT INTO Payments (JobId,WorkerId,Amount,Status,PaidAt,CreatedAt) "
           "VALUES (1,1,3200.0,'paid','2026-01-05','2026-01-04')")
db.execute("INSERT INTO Payments (JobId,WorkerId,Amount,Status,PaidAt,CreatedAt) "
           "VALUES (2,1,1537.45,'pending',NULL,'2026-01-04')")
db.execute("INSERT INTO Ratings (JobId,AuthorId,SubjectId,Stars,Comment,SubjectRole,CreatedAt) "
           "VALUES (1,2,1,5,'Great work','worker','2026-01-06')")
db.commit()

before = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ["Users", "Jobs", "Applications", "Payments", "Ratings", "Notifications"]}
print("legacy row counts:", before, "\n")


# ---------------------------------------------------------------
# Re-implement the bootstrapper's control flow in Python, issuing
# the same SQL the C# emits.
# ---------------------------------------------------------------
def table_exists(c, t):
    return c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0] > 0

def column_exists(c, t, col):
    return any(r[1].lower() == col.lower() for r in c.execute(f'PRAGMA table_info("{t}")'))

def ensure_log(c):
    c.executescript('CREATE TABLE IF NOT EXISTS "SchemaUpgrades" ("Name" TEXT NOT NULL PRIMARY KEY, "AppliedAt" TEXT NOT NULL);')

def applied(c, name):
    return c.execute('SELECT COUNT(*) FROM "SchemaUpgrades" WHERE "Name"=?', (name,)).fetchone()[0] > 0

def mark(c, name):
    if not applied(c, name):
        c.execute('INSERT INTO "SchemaUpgrades" ("Name","AppliedAt") VALUES (?,?)', (name, "now"))

MARKER = "money-to-cents-v1"

def upgrade(c, fresh=False):
    """Mirrors DatabaseBootstrapper.EnsureUpToDate."""
    ensure_log(c)
    if fresh:
        mark(c, MARKER)
        return 0

    n = 0
    for table, column, definition in NEW_COLUMNS:
        if not table_exists(c, table):
            continue
        if column_exists(c, table, column):
            continue
        c.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition};')
        n += 1

    for table, ddl in NEW_TABLES:
        if table_exists(c, table):
            continue
        c.executescript(ddl)
        n += 1

    if not applied(c, MARKER):
        if table_exists(c, "Jobs"):
            c.execute('UPDATE "Jobs" SET "Pay" = CAST(ROUND("Pay" * 100) AS INTEGER);')
        if table_exists(c, "Payments"):
            c.execute('UPDATE "Payments" SET "Amount" = CAST(ROUND("Amount" * 100) AS INTEGER);')
            if column_exists(c, "Payments", "AgreedRate"):
                c.execute('UPDATE "Payments" SET "AgreedRate" = "Amount" WHERE "AgreedRate" = 0;')
            if column_exists(c, "Payments", "AmountPaid"):
                c.execute('UPDATE "Payments" SET "AmountPaid" = "Amount" WHERE "Status" = \'paid\' AND "AmountPaid" = 0;')
        mark(c, MARKER)
        n += 1
    return n


print("=== FIRST UPGRADE (legacy database) ===")
changes = upgrade(db)
db.commit()
print(f"  {changes} change(s) applied\n")

after = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
check("no rows lost", after == before, f"{before} -> {after}")

for table, column, _ in NEW_COLUMNS:
    if not column_exists(db, table, column):
        check(f"column {table}.{column} added", False)
        break
else:
    check(f"all {len(NEW_COLUMNS)} new columns added", True)

missing_tables = [t for t, _ in NEW_TABLES if not table_exists(db, t)]
check("all new tables created", not missing_tables, str(missing_tables))

# money conversion: 3200.00 rupees -> 320000 cents
pay1 = db.execute("SELECT Pay FROM Jobs WHERE Id=1").fetchone()[0]
check("whole-rupee wage converted exactly", int(pay1) == 320000, f"Pay={pay1} (expected 320000)")

pay2 = db.execute("SELECT Pay FROM Jobs WHERE Id=2").fetchone()[0]
check("fractional wage converted exactly", int(pay2) == 153745, f"Pay={pay2} (expected 153745)")

amt = db.execute("SELECT Amount, AgreedRate, AmountPaid, Status FROM Payments WHERE Id=1").fetchone()
check("paid payment amount converted", int(amt[0]) == 320000, f"Amount={amt[0]}")
check("AgreedRate back-filled", int(amt[1]) == 320000, f"AgreedRate={amt[1]}")
check("AmountPaid back-filled for settled payment", int(amt[2]) == 320000, f"AmountPaid={amt[2]}")

pend = db.execute("SELECT Amount, AmountPaid FROM Payments WHERE Id=2").fetchone()
check("pending payment keeps AmountPaid at zero", int(pend[1]) == 0, f"AmountPaid={pend[1]}")
check("pending payment amount converted", int(pend[0]) == 153745, f"Amount={pend[0]}")

check("existing user data intact",
      db.execute("SELECT Name FROM Users WHERE Id=1").fetchone()[0] == "Nimal Perera")
check("existing rating intact",
      db.execute("SELECT Comment FROM Ratings WHERE Id=1").fetchone()[0] == "Great work")
check("new columns defaulted sensibly",
      db.execute("SELECT IsActive, VerificationStatus FROM Users WHERE Id=1").fetchone() == (1, "unverified"))

print("\n=== SECOND UPGRADE (idempotency — the dangerous case) ===")
changes2 = upgrade(db)
db.commit()
check("second run applies no changes", changes2 == 0, f"{changes2} change(s)")

pay1b = db.execute("SELECT Pay FROM Jobs WHERE Id=1").fetchone()[0]
check("money NOT multiplied a second time", int(pay1b) == 320000, f"Pay={pay1b}")

after2 = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
check("still no rows lost", after2 == before)

print("\n=== FRESH DATABASE PATH ===")
fresh = sqlite3.connect(":memory:")
fresh.executescript('CREATE TABLE "Jobs" ("Id" INTEGER PRIMARY KEY, "Pay" INTEGER NOT NULL);')
fresh.execute('INSERT INTO Jobs (Id, Pay) VALUES (1, 250000);')   # already cents
upgrade(fresh, fresh=True)
fresh.commit()
v = fresh.execute("SELECT Pay FROM Jobs WHERE Id=1").fetchone()[0]
check("fresh database is never rescaled", int(v) == 250000, f"Pay={v}")
check("marker recorded on fresh install", applied(fresh, MARKER))

# A restart of a fresh install must also leave money alone.
upgrade(fresh)
fresh.commit()
v2 = fresh.execute("SELECT Pay FROM Jobs WHERE Id=1").fetchone()[0]
check("restart after fresh install leaves money alone", int(v2) == 250000, f"Pay={v2}")

print()
if fails:
    print("RESULT: FAILURES ->", fails)
    sys.exit(1)
print("RESULT: ALL DATABASE UPGRADE CHECKS PASSED")
