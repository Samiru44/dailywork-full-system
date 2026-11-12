using DailyWork.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace DailyWork.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<User> Users => Set<User>();
    public DbSet<Job> Jobs => Set<Job>();
    public DbSet<JobApplication> Applications => Set<JobApplication>();
    public DbSet<Payment> Payments => Set<Payment>();
    public DbSet<PaymentAudit> PaymentAudits => Set<PaymentAudit>();
    public DbSet<WorkRecord> WorkRecords => Set<WorkRecord>();
    public DbSet<Rating> Ratings => Set<Rating>();
    public DbSet<Notification> Notifications => Set<Notification>();
    public DbSet<JobCategory> JobCategories => Set<JobCategory>();
    public DbSet<ContactMessage> ContactMessages => Set<ContactMessage>();
    public DbSet<Project> Projects => Set<Project>();
    public DbSet<CvDocument> CvDocuments => Set<CvDocument>();

    /// <summary>
    /// Money is stored as a whole number of cents rather than a floating-point
    /// value. Every integer up to 2^53 is represented exactly in SQLite's numeric
    /// storage, so amounts round-trip without the drift that makes floating-point
    /// unsuitable for financial records, and SQL ORDER BY / SUM stay correct.
    /// All arithmetic in the application itself is done in C# decimal.
    /// </summary>
    private static readonly ValueConverter<decimal, long> MoneyConverter = new(
        value => (long)Math.Round(value * 100m, MidpointRounding.AwayFromZero),
        stored => stored / 100m);

    /// <summary>Units worked are stored the same way, to two decimal places.</summary>
    private static readonly ValueConverter<decimal, long> UnitsConverter = new(
        value => (long)Math.Round(value * 100m, MidpointRounding.AwayFromZero),
        stored => stored / 100m);

    protected override void OnModelCreating(ModelBuilder mb)
    {
        base.OnModelCreating(mb);

        // ---------------- Users ----------------
        mb.Entity<User>().HasIndex(u => u.Email).IsUnique();
        mb.Entity<User>().HasIndex(u => u.Role);
        mb.Entity<User>().HasIndex(u => u.VerificationStatus);

        // IsVerified is derived from VerificationStatus, never stored.
        mb.Entity<User>().Ignore(u => u.IsVerified);

        // ---------------- Jobs ----------------
        mb.Entity<Job>().Property(j => j.Pay).HasConversion(MoneyConverter);
        mb.Entity<Job>().HasIndex(j => j.Status);
        mb.Entity<Job>().HasIndex(j => j.Category);

        mb.Entity<Job>()
          .HasOne(j => j.Employer)
          .WithMany(u => u.JobsPosted)
          .HasForeignKey(j => j.EmployerId)
          .OnDelete(DeleteBehavior.Cascade);

        // A job may belong to an organization project. Deleting a project
        // leaves its jobs in place with no project rather than removing work
        // that people have applied to or been paid for.
        mb.Entity<Job>()
          .HasOne(j => j.Project)
          .WithMany(p => p.Jobs)
          .HasForeignKey(j => j.ProjectId)
          .OnDelete(DeleteBehavior.SetNull);

        mb.Entity<Project>().Property(p => p.Budget).HasConversion(MoneyConverter);
        mb.Entity<Project>().HasIndex(p => p.OrganizationId);

        mb.Entity<Project>()
          .HasOne(p => p.Organization)
          .WithMany()
          .HasForeignKey(p => p.OrganizationId)
          .OnDelete(DeleteBehavior.Cascade);

        // ---------------- Applications ----------------
        mb.Entity<JobApplication>()
          .HasOne(a => a.Job)
          .WithMany(j => j.Applications)
          .HasForeignKey(a => a.JobId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<JobApplication>()
          .HasOne(a => a.Worker)
          .WithMany(u => u.Applications)
          .HasForeignKey(a => a.WorkerId)
          .OnDelete(DeleteBehavior.Restrict);

        // one application per worker per job
        mb.Entity<JobApplication>()
          .HasIndex(a => new { a.JobId, a.WorkerId })
          .IsUnique();

        // ---------------- Payments ----------------
        mb.Entity<Payment>().Property(p => p.Amount).HasConversion(MoneyConverter);
        mb.Entity<Payment>().Property(p => p.AmountPaid).HasConversion(MoneyConverter);
        mb.Entity<Payment>().Property(p => p.AgreedRate).HasConversion(MoneyConverter);
        mb.Entity<Payment>().Property(p => p.UnitsWorked).HasConversion(UnitsConverter);

        mb.Entity<Payment>().Property(p => p.ConfirmedAmount).HasConversion(MoneyConverter);

        // Outstanding and AwaitingConfirmation are derived, never stored.
        mb.Entity<Payment>().Ignore(p => p.Outstanding);
        mb.Entity<Payment>().Ignore(p => p.AwaitingConfirmation);

        mb.Entity<Payment>()
          .HasOne(p => p.Job)
          .WithMany()
          .HasForeignKey(p => p.JobId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<Payment>()
          .HasOne(p => p.Worker)
          .WithMany(u => u.Payments)
          .HasForeignKey(p => p.WorkerId)
          .OnDelete(DeleteBehavior.Restrict);

        mb.Entity<Payment>()
          .HasOne(p => p.Application)
          .WithMany()
          .HasForeignKey(p => p.ApplicationId)
          .OnDelete(DeleteBehavior.SetNull);

        // exactly one payment per application
        mb.Entity<Payment>()
          .HasIndex(p => p.ApplicationId)
          .IsUnique()
          .HasFilter("\"ApplicationId\" IS NOT NULL");

        // ---------------- Payment audit ----------------
        mb.Entity<PaymentAudit>().Property(a => a.AmountAtChange).HasConversion(MoneyConverter);

        mb.Entity<PaymentAudit>()
          .HasOne(a => a.Payment)
          .WithMany(p => p.AuditTrail)
          .HasForeignKey(a => a.PaymentId)
          .OnDelete(DeleteBehavior.Cascade);

        // ---------------- Work records ----------------
        mb.Entity<WorkRecord>().Property(w => w.RateApplied).HasConversion(MoneyConverter);
        mb.Entity<WorkRecord>().Property(w => w.LineTotal).HasConversion(MoneyConverter);
        mb.Entity<WorkRecord>().Property(w => w.Units).HasConversion(UnitsConverter);

        mb.Entity<WorkRecord>()
          .HasOne(w => w.Job)
          .WithMany()
          .HasForeignKey(w => w.JobId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<WorkRecord>()
          .HasOne(w => w.Worker)
          .WithMany()
          .HasForeignKey(w => w.WorkerId)
          .OnDelete(DeleteBehavior.Restrict);

        mb.Entity<WorkRecord>()
          .HasOne(w => w.Application)
          .WithMany()
          .HasForeignKey(w => w.ApplicationId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<WorkRecord>().HasIndex(w => new { w.ApplicationId, w.WorkDate });

        // SubmittedByWorker is derived from SubmittedByUserId, never stored.
        mb.Entity<WorkRecord>().Ignore(w => w.SubmittedByWorker);

        // ---------------- Ratings ----------------
        mb.Entity<Rating>()
          .HasOne(r => r.Job)
          .WithMany()
          .HasForeignKey(r => r.JobId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<Rating>()
          .HasOne(r => r.Author)
          .WithMany()
          .HasForeignKey(r => r.AuthorId)
          .OnDelete(DeleteBehavior.Restrict);

        mb.Entity<Rating>()
          .HasOne(r => r.Subject)
          .WithMany()
          .HasForeignKey(r => r.SubjectId)
          .OnDelete(DeleteBehavior.Restrict);

        // one review per author per job
        mb.Entity<Rating>()
          .HasIndex(r => new { r.JobId, r.AuthorId })
          .IsUnique();

        // ---------------- CVs ----------------
        // One CV per account. Deleting the account deletes the file with it.
        mb.Entity<CvDocument>()
          .HasOne(c => c.User)
          .WithMany()
          .HasForeignKey(c => c.UserId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<CvDocument>()
          .HasIndex(c => c.UserId)
          .IsUnique();

        // ---------------- Notifications ----------------
        mb.Entity<Notification>()
          .HasOne(n => n.User)
          .WithMany(u => u.Notifications)
          .HasForeignKey(n => n.UserId)
          .OnDelete(DeleteBehavior.Cascade);

        mb.Entity<Notification>().HasIndex(n => new { n.UserId, n.IsRead });

        // ---------------- Job categories ----------------
        mb.Entity<JobCategory>().HasIndex(c => c.Name).IsUnique();

        // ---------------- Contact messages ----------------
        mb.Entity<ContactMessage>().HasIndex(c => c.Status);
    }
}
