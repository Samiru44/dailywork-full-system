using System.Globalization;
using System.Security.Claims;
using System.Text;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Dashboard reports. Every figure is calculated from stored records — nothing
/// here is illustrative. Each report also exposes a CSV download so the numbers
/// can be taken into a spreadsheet.
/// </summary>
[ApiController]
[Route("api/reports")]
[Authorize]
public class ReportsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly EmailQueue _email;

    public ReportsController(AppDbContext db, EmailQueue email)
    {
        _db = db;
        _email = email;
    }

    private static readonly CultureInfo Plain = CultureInfo.InvariantCulture;

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    // =================================================================
    // Worker
    // =================================================================

    /// <summary>GET /api/reports/worker</summary>
    [HttpGet("worker")]
    public async Task<ActionResult> WorkerReport()
    {
        var me = CurrentUserId;

        var apps = await _db.Applications
            .Where(a => a.WorkerId == me)
            .Include(a => a.Job)
            .ToListAsync();

        var payments = await _db.Payments
            .Where(p => p.WorkerId == me)
            .Include(p => p.Job)
            .ToListAsync();

        var earningsByMonth = payments
            .Where(p => p.AmountPaid > 0)
            .GroupBy(p => new { (p.PaidAt ?? p.CreatedAt).Year, (p.PaidAt ?? p.CreatedAt).Month })
            .OrderBy(g => g.Key.Year).ThenBy(g => g.Key.Month)
            .Select(g => new
            {
                month = $"{g.Key.Year}-{g.Key.Month:00}",
                label = new DateTime(g.Key.Year, g.Key.Month, 1).ToString("MMM yyyy", CultureInfo.InvariantCulture),
                amount = g.Sum(p => p.AmountPaid),
                jobs = g.Count()
            })
            .ToList();

        var byCategory = apps
            .Where(a => a.Status == "completed" && a.Job is not null)
            .GroupBy(a => a.Job!.Category)
            .Select(g => new { category = g.Key, jobs = g.Count() })
            .OrderByDescending(x => x.jobs)
            .ToList();

        var stars = await _db.Ratings.Where(r => r.SubjectId == me).Select(r => r.Stars).ToListAsync();

        return Ok(new
        {
            applied        = apps.Count,
            pending        = apps.Count(a => a.Status == "pending"),
            shortlisted    = apps.Count(a => a.Status == "shortlisted"),
            hired          = apps.Count(a => a.Status == "accepted"),
            completed      = apps.Count(a => a.Status == "completed"),
            rejected       = apps.Count(a => a.Status == "rejected"),
            successRate    = apps.Count == 0 ? 0
                             : Math.Round(apps.Count(a => a.Status is "accepted" or "completed") * 100.0 / apps.Count, 1),
            totalEarned    = payments.Sum(p => p.AmountPaid),
            pendingWages   = payments.Sum(p => p.Amount - p.AmountPaid),
            paymentRecords = payments.Count,
            awaitingConfirmation = payments.Count(p => p.AmountPaid > 0 && !p.WorkerConfirmed),
            averageRating  = stars.Count > 0 ? Math.Round(stars.Average(), 1) : 0,
            ratingCount    = stars.Count,
            earningsByMonth,
            byCategory
        });
    }

    /// <summary>GET /api/reports/worker/payments.csv</summary>
    [HttpGet("worker/payments.csv")]
    public async Task<IActionResult> WorkerPaymentsCsv()
    {
        var csv = await BuildWorkerPaymentsCsvAsync(CurrentUserId);
        return File(Encoding.UTF8.GetBytes(csv), "text/csv", "dailywork-payments.csv");
    }

    private async Task<string> BuildWorkerPaymentsCsvAsync(int me)
    {
        var rows = await _db.Payments
            .Where(p => p.WorkerId == me)
            .Include(p => p.Job).ThenInclude(j => j!.Employer)
            .OrderByDescending(p => p.CreatedAt)
            .ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("Job,Employer,Rate,Unit,UnitsWorked,AmountDue,AmountPaid,Outstanding,Status,Confirmed,RaisedOn,PaidOn");

        foreach (var p in rows)
        {
            csv.AppendLine(string.Join(",",
                Csv(p.Job?.Title), Csv(p.Job?.Employer?.Name),
                p.AgreedRate.ToString("0.00", CultureInfo.InvariantCulture),
                Csv(p.RateUnit),
                p.UnitsWorked.ToString("0.##", CultureInfo.InvariantCulture),
                p.Amount.ToString("0.00", CultureInfo.InvariantCulture),
                p.AmountPaid.ToString("0.00", CultureInfo.InvariantCulture),
                (p.Amount - p.AmountPaid).ToString("0.00", CultureInfo.InvariantCulture),
                Csv(p.Status),
                p.WorkerConfirmed ? "yes" : "no",
                p.CreatedAt.ToString("yyyy-MM-dd"),
                p.PaidAt?.ToString("yyyy-MM-dd") ?? ""));
        }

        return csv.ToString();
    }

    // =================================================================
    // Employer and organization
    // =================================================================

    /// <summary>GET /api/reports/employer</summary>
    [HttpGet("employer")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<ActionResult> EmployerReport()
    {
        var me = CurrentUserId;

        var jobs = await _db.Jobs.Where(j => j.EmployerId == me).ToListAsync();
        var jobIds = jobs.Select(j => j.Id).ToList();

        var apps = await _db.Applications
            .Where(a => jobIds.Contains(a.JobId))
            .ToListAsync();

        var payments = await _db.Payments
            .Where(p => jobIds.Contains(p.JobId))
            .ToListAsync();

        var postingsByMonth = jobs
            .GroupBy(j => new { j.CreatedAt.Year, j.CreatedAt.Month })
            .OrderBy(g => g.Key.Year).ThenBy(g => g.Key.Month)
            .Select(g => new
            {
                month = $"{g.Key.Year}-{g.Key.Month:00}",
                label = new DateTime(g.Key.Year, g.Key.Month, 1).ToString("MMM yyyy", CultureInfo.InvariantCulture),
                posted = g.Count()
            })
            .ToList();

        var byCategory = jobs
            .GroupBy(j => j.Category)
            .Select(g => new
            {
                category = g.Key,
                posted = g.Count(),
                applicants = apps.Count(a => g.Select(x => x.Id).Contains(a.JobId))
            })
            .OrderByDescending(x => x.posted)
            .ToList();

        var spendByMonth = payments
            .Where(p => p.AmountPaid > 0)
            .GroupBy(p => new { (p.PaidAt ?? p.CreatedAt).Year, (p.PaidAt ?? p.CreatedAt).Month })
            .OrderBy(g => g.Key.Year).ThenBy(g => g.Key.Month)
            .Select(g => new
            {
                month = $"{g.Key.Year}-{g.Key.Month:00}",
                label = new DateTime(g.Key.Year, g.Key.Month, 1).ToString("MMM yyyy", CultureInfo.InvariantCulture),
                amount = g.Sum(p => p.AmountPaid)
            })
            .ToList();

        return Ok(new
        {
            jobsPosted    = jobs.Count,
            openJobs      = jobs.Count(j => j.Status == "open"),
            closedJobs    = jobs.Count(j => j.Status == "closed"),
            totalApplicants = apps.Count,
            pendingReview = apps.Count(a => a.Status == "pending"),
            shortlisted   = apps.Count(a => a.Status == "shortlisted"),
            hired         = apps.Count(a => a.Status == "accepted"),
            completed     = apps.Count(a => a.Status == "completed"),
            rejected      = apps.Count(a => a.Status == "rejected"),
            fillRate      = jobs.Count == 0 ? 0
                            : Math.Round(apps.Count(a => a.Status is "accepted" or "completed") * 100.0 / Math.Max(jobs.Sum(j => j.WorkersNeeded), 1), 1),
            averageApplicantsPerJob = jobs.Count == 0 ? 0 : Math.Round((double)apps.Count / jobs.Count, 1),
            totalSpent    = payments.Sum(p => p.AmountPaid),
            outstanding   = payments.Sum(p => p.Amount - p.AmountPaid),
            paymentRecords = payments.Count,
            postingsByMonth,
            spendByMonth,
            byCategory
        });
    }

    /// <summary>GET /api/reports/employer/payments.csv</summary>
    [HttpGet("employer/payments.csv")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<IActionResult> EmployerPaymentsCsv()
    {
        var csv = await BuildEmployerPaymentsCsvAsync(CurrentUserId);
        return File(Encoding.UTF8.GetBytes(csv), "text/csv", "dailywork-employer-payments.csv");
    }

    private async Task<string> BuildEmployerPaymentsCsvAsync(int me)
    {
        var jobIds = await _db.Jobs.Where(j => j.EmployerId == me).Select(j => j.Id).ToListAsync();

        var rows = await _db.Payments
            .Where(p => jobIds.Contains(p.JobId))
            .Include(p => p.Job)
            .Include(p => p.Worker)
            .OrderByDescending(p => p.CreatedAt)
            .ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("Job,Worker,Rate,Unit,UnitsWorked,AmountDue,AmountPaid,Outstanding,Status,WorkerConfirmed,RaisedOn,PaidOn");

        foreach (var p in rows)
        {
            csv.AppendLine(string.Join(",",
                Csv(p.Job?.Title), Csv(p.Worker?.Name),
                p.AgreedRate.ToString("0.00", CultureInfo.InvariantCulture),
                Csv(p.RateUnit),
                p.UnitsWorked.ToString("0.##", CultureInfo.InvariantCulture),
                p.Amount.ToString("0.00", CultureInfo.InvariantCulture),
                p.AmountPaid.ToString("0.00", CultureInfo.InvariantCulture),
                (p.Amount - p.AmountPaid).ToString("0.00", CultureInfo.InvariantCulture),
                Csv(p.Status),
                p.WorkerConfirmed ? "yes" : "no",
                p.CreatedAt.ToString("yyyy-MM-dd"),
                p.PaidAt?.ToString("yyyy-MM-dd") ?? ""));
        }

        return csv.ToString();
    }

    // =================================================================
    // Administrator
    // =================================================================

    /// <summary>GET /api/reports/admin</summary>
    [HttpGet("admin")]
    [Authorize(Roles = "admin")]
    public async Task<ActionResult> AdminReport()
    {
        var users = await _db.Users
            .Select(u => new { u.Role, u.CreatedAt, u.IsActive, u.VerificationStatus })
            .ToListAsync();

        var jobs = await _db.Jobs.Select(j => new { j.Category, j.CreatedAt, j.Status }).ToListAsync();
        var apps = await _db.Applications.Select(a => new { a.Status, a.CreatedAt }).ToListAsync();
        var payments = await _db.Payments.Select(p => new { p.Amount, p.AmountPaid, p.Status, p.CreatedAt }).ToListAsync();

        var signupsByMonth = users
            .GroupBy(u => new { u.CreatedAt.Year, u.CreatedAt.Month })
            .OrderBy(g => g.Key.Year).ThenBy(g => g.Key.Month)
            .Select(g => new
            {
                month = $"{g.Key.Year}-{g.Key.Month:00}",
                label = new DateTime(g.Key.Year, g.Key.Month, 1).ToString("MMM yyyy", CultureInfo.InvariantCulture),
                users = g.Count()
            })
            .ToList();

        var jobsByMonth = jobs
            .GroupBy(j => new { j.CreatedAt.Year, j.CreatedAt.Month })
            .OrderBy(g => g.Key.Year).ThenBy(g => g.Key.Month)
            .Select(g => new
            {
                month = $"{g.Key.Year}-{g.Key.Month:00}",
                label = new DateTime(g.Key.Year, g.Key.Month, 1).ToString("MMM yyyy", CultureInfo.InvariantCulture),
                posted = g.Count()
            })
            .ToList();

        return Ok(new
        {
            totalUsers    = users.Count,
            activeUsers   = users.Count(u => u.IsActive),
            byRole = new
            {
                workers       = users.Count(u => u.Role == "worker"),
                employers     = users.Count(u => u.Role == "employer"),
                organizations = users.Count(u => u.Role == "organization"),
                admins        = users.Count(u => u.Role == "admin")
            },
            verification = new
            {
                verified   = users.Count(u => u.VerificationStatus == "verified"),
                pending    = users.Count(u => u.VerificationStatus == "pending"),
                rejected   = users.Count(u => u.VerificationStatus == "rejected"),
                unverified = users.Count(u => u.VerificationStatus == "unverified")
            },
            jobsPosted    = jobs.Count,
            openJobs      = jobs.Count(j => j.Status == "open"),
            applications  = apps.Count,
            completedJobs = apps.Count(a => a.Status == "completed"),
            payments = new
            {
                records     = payments.Count,
                totalDue    = payments.Sum(p => p.Amount),
                totalPaid   = payments.Sum(p => p.AmountPaid),
                outstanding = payments.Sum(p => p.Amount - p.AmountPaid)
            },
            jobsByCategory = jobs.GroupBy(j => j.Category)
                                 .Select(g => new { category = g.Key, count = g.Count() })
                                 .OrderByDescending(x => x.count).ToList(),
            signupsByMonth,
            jobsByMonth,
            newMessages = await _db.ContactMessages.CountAsync(m => m.Status == "new")
        });
    }

    /// <summary>GET /api/reports/admin/users.csv</summary>
    [HttpGet("admin/users.csv")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> AdminUsersCsv()
    {
        var rows = await _db.Users.OrderBy(u => u.Id).ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("Id,Name,Email,Phone,Role,District,Active,VerificationStatus,JoinedOn");

        foreach (var u in rows)
        {
            csv.AppendLine(string.Join(",",
                u.Id, Csv(u.Name), Csv(u.Email), Csv(u.Phone), Csv(u.Role),
                Csv(u.District), u.IsActive ? "yes" : "no",
                Csv(u.VerificationStatus), u.CreatedAt.ToString("yyyy-MM-dd")));
        }

        return File(Encoding.UTF8.GetBytes(csv.ToString()), "text/csv", "dailywork-users.csv");
    }

    /// <summary>GET /api/reports/admin/jobs.csv</summary>
    [HttpGet("admin/jobs.csv")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> AdminJobsCsv()
    {
        var csv = await BuildAdminJobsCsvAsync();
        return File(Encoding.UTF8.GetBytes(csv), "text/csv", "dailywork-jobs.csv");
    }

    private async Task<string> BuildAdminJobsCsvAsync()
    {
        var rows = await _db.Jobs
            .Include(j => j.Employer)
            .Include(j => j.Applications)
            .OrderBy(j => j.Id)
            .ToListAsync();

        var csv = new StringBuilder();
        csv.AppendLine("Id,Title,Category,Location,District,Rate,Unit,WorkersNeeded,Status,Employer,Applicants,PostedOn");

        foreach (var j in rows)
        {
            csv.AppendLine(string.Join(",",
                j.Id, Csv(j.Title), Csv(j.Category), Csv(j.Location), Csv(j.District),
                j.Pay.ToString("0.00", CultureInfo.InvariantCulture), Csv(j.Per),
                j.WorkersNeeded, Csv(j.Status), Csv(j.Employer?.Name),
                j.Applications.Count, j.CreatedAt.ToString("yyyy-MM-dd")));
        }

        return csv.ToString();
    }

    // =================================================================
    // Email a report
    // =================================================================

    /// <summary>
    /// POST /api/reports/email   body: { "report": "worker" | "employer" | "admin" }
    ///
    /// Emails the signed-in user one of their own reports: the headline figures
    /// in the message, and the detailed records attached as a CSV file.
    ///
    /// It only ever goes to the address on the caller's own account, so it
    /// cannot be used to send mail to anybody else, and each report has the
    /// same access rule as the page that shows it.
    /// </summary>
    [HttpPost("email")]
    public async Task<ActionResult> EmailReport([FromBody] ReportEmailDto dto)
    {
        var me = CurrentUserId;
        var kind = (dto.Report ?? "").Trim().ToLowerInvariant();

        var isAdmin = this.User.IsInRole("admin");
        var isEmployerSide = isAdmin || this.User.IsInRole("employer") || this.User.IsInRole("organization");

        if (kind != "worker" && kind != "employer" && kind != "admin")
            return BadRequest(new { message = "Please choose which report to send." });

        if (kind == "admin" && !isAdmin) return Forbid();
        if (kind == "employer" && !isEmployerSide) return Forbid();

        var user = await _db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == me);
        if (user is null) return NotFound(new { message = "User not found." });

        // Say plainly when the report cannot be emailed, instead of pretending.
        var delivery = _email.DeliveryFor(user.Email);

        if (delivery == EmailDelivery.Off)
        {
            if (EmailQueue.IsDemoAddress(user.Email) && _email.Mode == EmailDelivery.Smtp)
                return BadRequest(new
                {
                    message = "This is a demonstration account, and its email address (" + user.Email +
                              ") is not a real mailbox, so the report cannot be emailed to it. " +
                              "You can still download it with the Export button."
                });

            return StatusCode(StatusCodes.Status503ServiceUnavailable, new
            {
                message = "Email has not been set up on this server yet, so the report could not be sent. " +
                          "You can still download it with the Export button."
            });
        }

        if (!_email.TryStartReport(me, out var secondsToWait))
            return StatusCode(StatusCodes.Status429TooManyRequests, new
            {
                message = "A report was sent a moment ago. Please wait " + secondsToWait +
                          " seconds before sending another."
            });

        string title;
        List<(string Label, string Value)> figures;
        var files = new List<EmailAttachment>();

        if (kind == "admin")
        {
            title = "DailyWork platform report";
            figures = await AdminFiguresAsync();

            // The jobs list is attached. The users list is not: it holds every
            // member's phone number and email address, which should stay inside
            // the system rather than sit in a mailbox.
            files.Add(CsvFile("dailywork-jobs.csv", await BuildAdminJobsCsvAsync()));
        }
        else if (kind == "employer")
        {
            title = "Your DailyWork hiring report";
            figures = await EmployerFiguresAsync(me);
            files.Add(CsvFile("dailywork-employer-payments.csv", await BuildEmployerPaymentsCsvAsync(me)));
        }
        else
        {
            title = "Your DailyWork work report";
            figures = await WorkerFiguresAsync(me);
            files.Add(CsvFile("dailywork-payments.csv", await BuildWorkerPaymentsCsvAsync(me)));
        }

        if (!_email.Enqueue(EmailTemplates.Report(user, title, figures, files)))
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new
            {
                message = "The report could not be sent just now. Please try again in a minute."
            });

        if (delivery == EmailDelivery.Outbox)
            return Ok(new
            {
                delivery = "outbox",
                message = "No mail server is set up for " + user.Email + " to be reached, so the report " +
                          "was saved in the server's email outbox folder instead of being sent."
            });

        return Ok(new
        {
            delivery = "smtp",
            message = "Your report is on its way to " + user.Email + "."
        });
    }

    private static EmailAttachment CsvFile(string fileName, string csv) => new()
    {
        FileName = fileName,
        ContentType = "text/csv",

        // The leading byte-order mark tells Excel the file is UTF-8, so names
        // written in Sinhala or Tamil open correctly.
        Data = Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(csv)).ToArray()
    };

    private static string Count(int value) => value.ToString(Plain);

    private async Task<List<(string Label, string Value)>> WorkerFiguresAsync(int me)
    {
        var statuses = await _db.Applications
            .Where(a => a.WorkerId == me)
            .Select(a => a.Status)
            .ToListAsync();

        var payments = await _db.Payments
            .Where(p => p.WorkerId == me)
            .Select(p => new { p.Amount, p.AmountPaid })
            .ToListAsync();

        var stars = await _db.Ratings.Where(r => r.SubjectId == me).Select(r => r.Stars).ToListAsync();

        var won = statuses.Count(s => s is "accepted" or "completed");
        var successRate = statuses.Count == 0 ? 0.0 : Math.Round(won * 100.0 / statuses.Count, 1);

        return new List<(string Label, string Value)>
        {
            ("Jobs applied for", Count(statuses.Count)),
            ("Waiting for a decision", Count(statuses.Count(s => s == "pending"))),
            ("Shortlisted", Count(statuses.Count(s => s == "shortlisted"))),
            ("Currently hired", Count(statuses.Count(s => s == "accepted"))),
            ("Jobs completed", Count(statuses.Count(s => s == "completed"))),
            ("Not successful", Count(statuses.Count(s => s == "rejected"))),
            ("Success rate", successRate.ToString("0.#", Plain) + "%"),
            ("Total earned", EmailTemplates.Money(payments.Sum(p => p.AmountPaid))),
            ("Wages still owed to you", EmailTemplates.Money(payments.Sum(p => p.Amount - p.AmountPaid))),
            ("Average rating", stars.Count == 0
                ? "No reviews yet"
                : Math.Round(stars.Average(), 1).ToString("0.0", Plain) + " out of 5, from " +
                  Count(stars.Count) + " review(s)")
        };
    }

    private async Task<List<(string Label, string Value)>> EmployerFiguresAsync(int me)
    {
        var jobs = await _db.Jobs
            .Where(j => j.EmployerId == me)
            .Select(j => new { j.Id, j.Status, j.WorkersNeeded })
            .ToListAsync();

        var jobIds = jobs.Select(j => j.Id).ToList();

        var statuses = await _db.Applications
            .Where(a => jobIds.Contains(a.JobId))
            .Select(a => a.Status)
            .ToListAsync();

        var payments = await _db.Payments
            .Where(p => jobIds.Contains(p.JobId))
            .Select(p => new { p.Amount, p.AmountPaid })
            .ToListAsync();

        var filled = statuses.Count(s => s is "accepted" or "completed");
        var fillRate = jobs.Count == 0
            ? 0.0
            : Math.Round(filled * 100.0 / Math.Max(jobs.Sum(j => j.WorkersNeeded), 1), 1);

        return new List<(string Label, string Value)>
        {
            ("Jobs posted", Count(jobs.Count)),
            ("Open jobs", Count(jobs.Count(j => j.Status == "open"))),
            ("Total applicants", Count(statuses.Count)),
            ("Awaiting your review", Count(statuses.Count(s => s == "pending"))),
            ("Shortlisted", Count(statuses.Count(s => s == "shortlisted"))),
            ("Currently hired", Count(statuses.Count(s => s == "accepted"))),
            ("Jobs completed", Count(statuses.Count(s => s == "completed"))),
            ("Positions filled", fillRate.ToString("0.#", Plain) + "%"),
            ("Total paid to workers", EmailTemplates.Money(payments.Sum(p => p.AmountPaid))),
            ("Still outstanding", EmailTemplates.Money(payments.Sum(p => p.Amount - p.AmountPaid)))
        };
    }

    private async Task<List<(string Label, string Value)>> AdminFiguresAsync()
    {
        var users = await _db.Users
            .Select(u => new { u.Role, u.IsActive, u.VerificationStatus })
            .ToListAsync();

        var jobStatuses = await _db.Jobs.Select(j => j.Status).ToListAsync();
        var appStatuses = await _db.Applications.Select(a => a.Status).ToListAsync();

        var payments = await _db.Payments
            .Select(p => new { p.Amount, p.AmountPaid })
            .ToListAsync();

        return new List<(string Label, string Value)>
        {
            ("Total users", Count(users.Count)),
            ("Active users", Count(users.Count(u => u.IsActive))),
            ("Workers", Count(users.Count(u => u.Role == "worker"))),
            ("Employers", Count(users.Count(u => u.Role == "employer"))),
            ("Organizations", Count(users.Count(u => u.Role == "organization"))),
            ("Verified organizations", Count(users.Count(u => u.VerificationStatus == "verified"))),
            ("Awaiting verification", Count(users.Count(u => u.VerificationStatus == "pending"))),
            ("Jobs posted", Count(jobStatuses.Count)),
            ("Open jobs", Count(jobStatuses.Count(s => s == "open"))),
            ("Applications", Count(appStatuses.Count)),
            ("Jobs completed", Count(appStatuses.Count(s => s == "completed"))),
            ("Payment records", Count(payments.Count)),
            ("Total paid", EmailTemplates.Money(payments.Sum(p => p.AmountPaid))),
            ("Outstanding", EmailTemplates.Money(payments.Sum(p => p.Amount - p.AmountPaid)))
        };
    }

    // =================================================================

    /// <summary>Escapes a value for CSV so commas and quotes cannot break a row.</summary>
    private static string Csv(string? value)
    {
        var v = value ?? "";
        if (v.Contains(',') || v.Contains('"') || v.Contains('\n') || v.Contains('\r'))
            return "\"" + v.Replace("\"", "\"\"") + "\"";
        return v;
    }
}
