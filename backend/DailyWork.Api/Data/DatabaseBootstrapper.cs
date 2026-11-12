using System.Data.Common;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Data;

/// <summary>
/// Brings the database up to the current schema without destroying anything.
///
/// A fresh install gets the full schema created from the model. An install that
/// already holds data from an earlier version keeps every row: missing columns
/// and tables are added in place with ALTER TABLE / CREATE TABLE, which SQLite
/// performs without rewriting existing rows.
///
/// For a production deployment this would be replaced by generated EF Core
/// migrations; the commands for that are in docs/DATABASE.md. This bootstrapper
/// exists so an existing dailywork.db keeps working after an upgrade instead of
/// having to be deleted.
/// </summary>
public static class DatabaseBootstrapper
{
    /// <summary>One-off data migrations, recorded so they can never run twice.</summary>
    private const string MoneyToCentsMarker = "money-to-cents-v1";
    private const string ConfirmedAmountMarker = "confirmed-amount-v1";

    public static void EnsureUpToDate(AppDbContext db, ILogger logger)
    {
        // Creates the database and the full current schema when it does not
        // exist yet; returns false when the database was already present.
        var created = db.Database.EnsureCreated();

        var connection = db.Database.GetDbConnection();
        var opened = false;
        if (connection.State != System.Data.ConnectionState.Open)
        {
            connection.Open();
            opened = true;
        }

        try
        {
            EnsureUpgradeLog(connection);

            if (created)
            {
                // A brand-new database is built from the current model, so its
                // money columns already hold cents. Recording the marker now
                // guarantees the legacy conversion never runs against them.
                MarkApplied(connection, MoneyToCentsMarker);

                // Likewise, a new database has no payments confirmed under the
                // old one-way flag, so there is nothing to back-fill.
                MarkApplied(connection, ConfirmedAmountMarker);

                logger.LogInformation("Database created with the current schema.");
                return;
            }

            logger.LogInformation("Existing database found — checking for schema updates.");

            // Tables are created before columns are added, so a table created
            // by this run already carries every column its DDL declares and the
            // column pass finds nothing left to do. The other way round, a newly
            // created table would be missing any column added in a later release
            // until the application was restarted a second time — and would be
            // queried in between with those columns absent.
            var changes = AddMissingTables(connection, logger)
                        + AddMissingColumns(connection, logger)
                        + ConvertMoneyToCents(connection, logger)
                        + BackfillConfirmedAmounts(connection, logger);

            logger.LogInformation(changes == 0
                ? "Database schema is already up to date."
                : "Database upgraded in place: {Count} change(s) applied. Existing data preserved.",
                changes);
        }
        finally
        {
            if (opened) connection.Close();
        }
    }

    // =================================================================
    // Schema additions
    // =================================================================

    private static int AddMissingColumns(DbConnection connection, ILogger logger)
    {
        var applied = 0;

        foreach (var (table, column, definition) in NewColumns)
        {
            if (!TableExists(connection, table)) continue;   // created by AddMissingTables
            if (ColumnExists(connection, table, column)) continue;

            Execute(connection, $"ALTER TABLE \"{table}\" ADD COLUMN \"{column}\" {definition};");
            logger.LogInformation("Added column {Table}.{Column}", table, column);
            applied++;
        }

        return applied;
    }

    private static int AddMissingTables(DbConnection connection, ILogger logger)
    {
        var applied = 0;

        foreach (var (table, ddl) in NewTables)
        {
            if (TableExists(connection, table)) continue;

            Execute(connection, ddl);
            logger.LogInformation("Created table {Table}", table);
            applied++;
        }

        return applied;
    }

    /// <summary>
    /// Worker confirmation used to be a single true/false flag, which could not
    /// say how much had been confirmed. Payments already marked confirmed are
    /// treated as having confirmed everything recorded as paid at that moment,
    /// so nobody is asked to confirm the same money twice.
    ///
    /// Guarded by its own marker so it runs once and never re-runs.
    /// </summary>
    private static int BackfillConfirmedAmounts(DbConnection connection, ILogger logger)
    {
        if (AlreadyApplied(connection, ConfirmedAmountMarker)) return 0;

        if (!TableExists(connection, "Payments") ||
            !ColumnExists(connection, "Payments", "ConfirmedAmount") ||
            !ColumnExists(connection, "Payments", "WorkerConfirmed"))
            return 0;

        Execute(connection,
            "UPDATE \"Payments\" SET \"ConfirmedAmount\" = \"AmountPaid\" " +
            "WHERE \"WorkerConfirmed\" = 1 AND \"ConfirmedAmount\" = 0;");

        MarkApplied(connection, ConfirmedAmountMarker);
        logger.LogInformation("Back-filled confirmed payment amounts from the old confirmation flag.");
        return 1;
    }

    /// <summary>(table, column, SQLite column definition)</summary>
    private static readonly (string Table, string Column, string Definition)[] NewColumns =
    {
        // Users — account state
        ("Users", "IsActive",            "INTEGER NOT NULL DEFAULT 1"),
        ("Users", "DeactivatedAt",       "TEXT NULL"),
        ("Users", "DeactivationReason",  "TEXT NOT NULL DEFAULT ''"),
        ("Users", "SecurityStamp",       "TEXT NOT NULL DEFAULT '0001-01-01 00:00:00'"),

        // Users — extended profile
        ("Users", "District",            "TEXT NOT NULL DEFAULT ''"),
        ("Users", "Experience",          "TEXT NOT NULL DEFAULT ''"),
        ("Users", "ExperienceYears",     "INTEGER NOT NULL DEFAULT 0"),
        ("Users", "Certifications",      "TEXT NOT NULL DEFAULT ''"),

        // Users — organization verification
        ("Users", "VerificationStatus",       "TEXT NOT NULL DEFAULT 'unverified'"),
        ("Users", "OrganizationName",         "TEXT NOT NULL DEFAULT ''"),
        ("Users", "RegistrationNumber",       "TEXT NOT NULL DEFAULT ''"),
        ("Users", "OrganizationAddress",      "TEXT NOT NULL DEFAULT ''"),
        ("Users", "OrganizationWebsite",      "TEXT NOT NULL DEFAULT ''"),
        ("Users", "VerificationNotes",        "TEXT NOT NULL DEFAULT ''"),
        ("Users", "VerificationDecisionNote", "TEXT NOT NULL DEFAULT ''"),
        ("Users", "VerificationRequestedAt",  "TEXT NULL"),
        ("Users", "VerifiedAt",               "TEXT NULL"),
        ("Users", "VerifiedByUserId",         "INTEGER NULL"),

        // Jobs — richer posting details
        ("Jobs", "District",       "TEXT NOT NULL DEFAULT ''"),
        ("Jobs", "RequiredSkills", "TEXT NOT NULL DEFAULT ''"),
        ("Jobs", "WorkersNeeded",  "INTEGER NOT NULL DEFAULT 1"),
        ("Jobs", "ExpectedUnits",  "INTEGER NOT NULL DEFAULT 1"),
        ("Jobs", "StartDate",      "TEXT NULL"),
        ("Jobs", "EndDate",        "TEXT NULL"),
        ("Jobs", "UpdatedAt",      "TEXT NULL"),

        // Applications — lifecycle audit
        ("Applications", "Message",       "TEXT NOT NULL DEFAULT ''"),
        ("Applications", "ShortlistedAt", "TEXT NULL"),
        ("Applications", "AcceptedAt",    "TEXT NULL"),
        ("Applications", "RejectedAt",    "TEXT NULL"),
        ("Applications", "CompletedAt",   "TEXT NULL"),

        // Payments — wage breakdown and worker confirmation
        ("Payments", "ApplicationId",     "INTEGER NULL"),
        ("Payments", "AgreedRate",        "INTEGER NOT NULL DEFAULT 0"),
        ("Payments", "RateUnit",          "TEXT NOT NULL DEFAULT 'day'"),
        ("Payments", "UnitsWorked",       "INTEGER NOT NULL DEFAULT 100"),
        ("Payments", "AmountPaid",        "INTEGER NOT NULL DEFAULT 0"),
        ("Payments", "Method",            "TEXT NOT NULL DEFAULT ''"),
        ("Payments", "Notes",             "TEXT NOT NULL DEFAULT ''"),
        ("Payments", "WorkerConfirmed",   "INTEGER NOT NULL DEFAULT 0"),
        ("Payments", "WorkerConfirmedAt", "TEXT NULL"),
        ("Payments", "WorkerDisputeNote", "TEXT NOT NULL DEFAULT ''"),

        // How much of the amount paid the worker has actually confirmed.
        // Existing rows already marked confirmed are back-filled below, so a
        // payment confirmed under the old one-way flag is not re-asked for.
        ("Payments", "ConfirmedAmount",   "INTEGER NOT NULL DEFAULT 0"),

        // Worker-submitted work days wait for the employer's approval.
        // Existing records were all entered by the employer, so they default
        // to approved and nothing already counted towards a payment changes.
        ("WorkRecords", "Status",            "TEXT NOT NULL DEFAULT 'approved'"),
        ("WorkRecords", "SubmittedByUserId", "INTEGER NOT NULL DEFAULT 0"),
        ("WorkRecords", "DecisionNote",      "TEXT NOT NULL DEFAULT ''"),

        // Organization projects.
        ("Jobs", "ProjectId", "INTEGER NULL"),
    };

    private static readonly (string Table, string Ddl)[] NewTables =
    {
        ("Projects", """
            CREATE TABLE "Projects" (
                "Id"              INTEGER NOT NULL CONSTRAINT "PK_Projects" PRIMARY KEY AUTOINCREMENT,
                "OrganizationId"  INTEGER NOT NULL,
                "Name"            TEXT    NOT NULL DEFAULT '',
                "Description"     TEXT    NOT NULL DEFAULT '',
                "Location"        TEXT    NOT NULL DEFAULT '',
                "District"        TEXT    NOT NULL DEFAULT '',
                "WorkersRequired" INTEGER NOT NULL DEFAULT 0,
                "Budget"          INTEGER NOT NULL DEFAULT 0,
                "StartDate"       TEXT    NULL,
                "EndDate"         TEXT    NULL,
                "Status"          TEXT    NOT NULL DEFAULT 'planning',
                "CreatedAt"       TEXT    NOT NULL,
                "UpdatedAt"       TEXT    NULL,
                CONSTRAINT "FK_Projects_Users_OrganizationId"
                    FOREIGN KEY ("OrganizationId") REFERENCES "Users" ("Id") ON DELETE CASCADE
            );
            CREATE INDEX "IX_Projects_OrganizationId" ON "Projects" ("OrganizationId");
            """),

        ("CvDocuments", """
            CREATE TABLE "CvDocuments" (
                "Id"          INTEGER NOT NULL CONSTRAINT "PK_CvDocuments" PRIMARY KEY AUTOINCREMENT,
                "UserId"      INTEGER NOT NULL,
                "FileName"    TEXT    NOT NULL DEFAULT '',
                "ContentType" TEXT    NOT NULL DEFAULT '',
                "SizeBytes"   INTEGER NOT NULL DEFAULT 0,
                "Data"        BLOB    NOT NULL,
                "UploadedAt"  TEXT    NOT NULL,
                CONSTRAINT "FK_CvDocuments_Users_UserId"
                    FOREIGN KEY ("UserId") REFERENCES "Users" ("Id") ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX "IX_CvDocuments_UserId" ON "CvDocuments" ("UserId");
            """),

        ("PaymentAudits", """
            CREATE TABLE "PaymentAudits" (
                "Id"             INTEGER NOT NULL CONSTRAINT "PK_PaymentAudits" PRIMARY KEY AUTOINCREMENT,
                "PaymentId"      INTEGER NOT NULL,
                "Action"         TEXT    NOT NULL DEFAULT '',
                "FromStatus"     TEXT    NOT NULL DEFAULT '',
                "ToStatus"       TEXT    NOT NULL DEFAULT '',
                "AmountAtChange" INTEGER NOT NULL DEFAULT 0,
                "ActorUserId"    INTEGER NOT NULL DEFAULT 0,
                "ActorRole"      TEXT    NOT NULL DEFAULT '',
                "Note"           TEXT    NOT NULL DEFAULT '',
                "CreatedAt"      TEXT    NOT NULL,
                CONSTRAINT "FK_PaymentAudits_Payments_PaymentId"
                    FOREIGN KEY ("PaymentId") REFERENCES "Payments" ("Id") ON DELETE CASCADE
            );
            """),

        ("WorkRecords", """
            CREATE TABLE "WorkRecords" (
                "Id"            INTEGER NOT NULL CONSTRAINT "PK_WorkRecords" PRIMARY KEY AUTOINCREMENT,
                "JobId"         INTEGER NOT NULL,
                "WorkerId"      INTEGER NOT NULL,
                "ApplicationId" INTEGER NOT NULL,
                "WorkDate"      TEXT    NOT NULL,
                "Units"         INTEGER NOT NULL DEFAULT 100,
                "Unit"          TEXT    NOT NULL DEFAULT 'day',
                "RateApplied"   INTEGER NOT NULL DEFAULT 0,
                "LineTotal"     INTEGER NOT NULL DEFAULT 0,
                "Notes"         TEXT    NOT NULL DEFAULT '',
                "Verified"      INTEGER NOT NULL DEFAULT 0,
                "VerifiedAt"    TEXT    NULL,
                "Status"            TEXT    NOT NULL DEFAULT 'approved',
                "SubmittedByUserId" INTEGER NOT NULL DEFAULT 0,
                "DecisionNote"      TEXT    NOT NULL DEFAULT '',
                "CreatedAt"     TEXT    NOT NULL,
                CONSTRAINT "FK_WorkRecords_Jobs_JobId"
                    FOREIGN KEY ("JobId") REFERENCES "Jobs" ("Id") ON DELETE CASCADE,
                CONSTRAINT "FK_WorkRecords_Users_WorkerId"
                    FOREIGN KEY ("WorkerId") REFERENCES "Users" ("Id") ON DELETE RESTRICT,
                CONSTRAINT "FK_WorkRecords_Applications_ApplicationId"
                    FOREIGN KEY ("ApplicationId") REFERENCES "Applications" ("Id") ON DELETE CASCADE
            );
            """),

        ("JobCategories", """
            CREATE TABLE "JobCategories" (
                "Id"          INTEGER NOT NULL CONSTRAINT "PK_JobCategories" PRIMARY KEY AUTOINCREMENT,
                "Name"        TEXT    NOT NULL,
                "Description" TEXT    NOT NULL DEFAULT '',
                "Icon"        TEXT    NOT NULL DEFAULT 'fa-briefcase',
                "SortOrder"   INTEGER NOT NULL DEFAULT 0,
                "IsActive"    INTEGER NOT NULL DEFAULT 1,
                "CreatedAt"   TEXT    NOT NULL
            );
            """),

        ("ContactMessages", """
            CREATE TABLE "ContactMessages" (
                "Id"        INTEGER NOT NULL CONSTRAINT "PK_ContactMessages" PRIMARY KEY AUTOINCREMENT,
                "Name"      TEXT    NOT NULL DEFAULT '',
                "Email"     TEXT    NOT NULL DEFAULT '',
                "Subject"   TEXT    NOT NULL DEFAULT '',
                "Message"   TEXT    NOT NULL DEFAULT '',
                "Status"    TEXT    NOT NULL DEFAULT 'new',
                "UserId"    INTEGER NULL,
                "CreatedAt" TEXT    NOT NULL,
                "HandledAt" TEXT    NULL
            );
            """),
    };

    // =================================================================
    // One-off data conversion
    // =================================================================

    /// <summary>
    /// Earlier versions stored money as a floating-point number of rupees; the
    /// model now stores whole cents. This rescales legacy values exactly once —
    /// the marker row makes a second run impossible, which matters because
    /// running it twice would multiply every amount by a hundred.
    /// </summary>
    private static int ConvertMoneyToCents(DbConnection connection, ILogger logger)
    {
        if (AlreadyApplied(connection, MoneyToCentsMarker)) return 0;

        if (TableExists(connection, "Jobs"))
            Execute(connection, "UPDATE \"Jobs\" SET \"Pay\" = CAST(ROUND(\"Pay\" * 100) AS INTEGER);");

        if (TableExists(connection, "Payments"))
        {
            Execute(connection, "UPDATE \"Payments\" SET \"Amount\" = CAST(ROUND(\"Amount\" * 100) AS INTEGER);");

            // Back-fill the new wage columns from what the old rows already knew.
            if (ColumnExists(connection, "Payments", "AgreedRate"))
                Execute(connection,
                    "UPDATE \"Payments\" SET \"AgreedRate\" = \"Amount\" WHERE \"AgreedRate\" = 0;");

            if (ColumnExists(connection, "Payments", "AmountPaid"))
                Execute(connection,
                    "UPDATE \"Payments\" SET \"AmountPaid\" = \"Amount\" " +
                    "WHERE \"Status\" = 'paid' AND \"AmountPaid\" = 0;");
        }

        MarkApplied(connection, MoneyToCentsMarker);
        logger.LogInformation("Converted stored money values from rupees to whole cents.");
        return 1;
    }

    // =================================================================
    // Upgrade log
    // =================================================================

    private static void EnsureUpgradeLog(DbConnection connection) => Execute(connection, """
        CREATE TABLE IF NOT EXISTS "SchemaUpgrades" (
            "Name"      TEXT NOT NULL PRIMARY KEY,
            "AppliedAt" TEXT NOT NULL
        );
        """);

    private static bool AlreadyApplied(DbConnection connection, string name)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM \"SchemaUpgrades\" WHERE \"Name\" = $n;";
        AddParam(cmd, "$n", name);
        return Convert.ToInt64(cmd.ExecuteScalar() ?? 0L) > 0;
    }

    private static void MarkApplied(DbConnection connection, string name)
    {
        if (AlreadyApplied(connection, name)) return;

        using var cmd = connection.CreateCommand();
        cmd.CommandText = "INSERT INTO \"SchemaUpgrades\" (\"Name\", \"AppliedAt\") VALUES ($n, $t);";
        AddParam(cmd, "$n", name);
        AddParam(cmd, "$t", DateTime.UtcNow.ToString("o"));
        cmd.ExecuteNonQuery();
    }

    // =================================================================
    // Small SQLite helpers
    // =================================================================

    private static void AddParam(DbCommand cmd, string name, object value)
    {
        var p = cmd.CreateParameter();
        p.ParameterName = name;
        p.Value = value;
        cmd.Parameters.Add(p);
    }

    private static void Execute(DbConnection connection, string sql)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText = sql;
        cmd.ExecuteNonQuery();
    }

    private static bool TableExists(DbConnection connection, string table)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = $name;";
        AddParam(cmd, "$name", table);
        return Convert.ToInt64(cmd.ExecuteScalar() ?? 0L) > 0;
    }

    private static bool ColumnExists(DbConnection connection, string table, string column)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText = $"PRAGMA table_info(\"{table}\");";

        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            if (string.Equals(reader.GetString(1), column, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }
}
