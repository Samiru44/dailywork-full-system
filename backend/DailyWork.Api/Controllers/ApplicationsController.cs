using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

[ApiController]
[Route("api/applications")]
[Authorize]
public class ApplicationsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;
    private readonly EmailQueue _email;

    public ApplicationsController(AppDbContext db, NotificationService notify, EmailQueue email)
    {
        _db = db;
        _notify = notify;
        _email = email;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    // =================================================================
    // Apply for a job
    // =================================================================

    /// <summary>
    /// POST /api/applications  body: { "jobId": 1, "message": "optional" }
    ///
    /// Only workers may apply. Every rule below is enforced here on the server;
    /// hiding the button in the browser is not a security control.
    /// </summary>
    [HttpPost]
    [Authorize(Roles = "worker")]
    public async Task<ActionResult> Apply([FromBody] ApplyDto dto)
    {
        var me = CurrentUserId;

        var job = await _db.Jobs
            .Include(j => j.Applications)
            .FirstOrDefaultAsync(j => j.Id == dto.JobId);

        if (job is null)
            return NotFound(new { message = "Job not found." });

        if (job.Status != "open")
            return BadRequest(new { message = "This job is no longer accepting applications." });

        // A job whose end date has passed cannot be applied for.
        if (job.EndDate.HasValue && job.EndDate.Value.Date < DateTime.UtcNow.Date)
            return BadRequest(new { message = "This job has already finished." });

        // Nobody may apply to a job they posted themselves.
        if (job.EmployerId == me)
            return BadRequest(new { message = "You cannot apply to your own job posting." });

        // The account must still be active.
        var worker = await _db.Users.FindAsync(me);
        if (worker is null || !worker.IsActive)
            return Forbid();

        var existing = await _db.Applications
            .FirstOrDefaultAsync(a => a.JobId == dto.JobId && a.WorkerId == me);

        if (existing is not null)
        {
            // Being already hired is a clearer message than a plain duplicate.
            if (existing.Status is "accepted" or "completed")
                return Conflict(new { message = "You are already assigned to this job." });

            return Conflict(new { message = "You have already applied for this job." });
        }

        // Stop applications once the posting has hired everyone it needs.
        var hired = job.Applications.Count(a => a.Status is "accepted" or "completed");
        if (hired >= job.WorkersNeeded)
            return BadRequest(new { message = "This job has already hired all the workers it needs." });

        _db.Applications.Add(new JobApplication
        {
            JobId = dto.JobId,
            WorkerId = me,
            Message = (dto.Message ?? "").Trim(),
            Status = "pending"
        });

        _notify.Raise(job.EmployerId, "application", "New applicant",
            $"{worker.Name} applied for \"{job.Title}\".");

        await _db.SaveChangesAsync();

        // Email both sides. This happens only after the application is safely
        // stored, and a problem with email can never fail the application.
        await SendApplicationEmailsAsync(job, worker, dto.Message);

        return Ok(new { message = "Application submitted." });
    }

    /// <summary>
    /// Confirms the application to the worker and tells the employer who
    /// applied. The worker's CV, when they have one, is attached to the
    /// employer's copy: applying for a job is what shares it with that employer.
    /// </summary>
    private async Task SendApplicationEmailsAsync(Job job, User worker, string? note)
    {
        try
        {
            var employerId = job.EmployerId;
            var workerId = worker.Id;

            var employer = await _db.Users.AsNoTracking()
                .FirstOrDefaultAsync(u => u.Id == employerId);

            var cv = await _db.CvDocuments.AsNoTracking()
                .FirstOrDefaultAsync(c => c.UserId == workerId);

            _email.Enqueue(EmailTemplates.ApplicationReceived(
                worker, job, employer?.Name ?? "the employer", cv?.FileName));

            if (employer is not null && employer.IsActive)
                _email.Enqueue(EmailTemplates.NewApplicant(employer, worker, job, note, cv));
        }
        catch
        {
            // Email is in addition to the in-app notification, which has
            // already been saved. Failing to send it changes nothing else.
        }
    }

    // =================================================================
    // Worker's own applications
    // =================================================================

    /// <summary>GET /api/applications/mine</summary>
    [HttpGet("mine")]
    public async Task<ActionResult<IEnumerable<ApplicationDto>>> Mine()
    {
        var me = CurrentUserId;

        var apps = await _db.Applications
            .Where(a => a.WorkerId == me)
            .Include(a => a.Job).ThenInclude(j => j!.Employer)
            .OrderByDescending(a => a.CreatedAt)
            .Select(a => new ApplicationDto
            {
                Id = a.Id,
                JobId = a.JobId,
                JobTitle = a.Job!.Title,
                EmployerName = a.Job.Employer!.Name,
                Location = a.Job.Location,
                Pay = a.Job.Pay,
                Per = a.Job.Per,
                Status = a.Status,
                CreatedAt = a.CreatedAt,
                AcceptedAt = a.AcceptedAt,
                CompletedAt = a.CompletedAt
            })
            .ToListAsync();

        return Ok(apps);
    }

    /// <summary>GET /api/applications/job/5 — applicants for a job the caller owns.</summary>
    [HttpGet("job/{jobId:int}")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<ActionResult> ForJob(int jobId)
    {
        var job = await _db.Jobs.FindAsync(jobId);
        if (job is null) return NotFound(new { message = "Job not found." });
        if (job.EmployerId != CurrentUserId && !this.User.IsInRole("admin")) return Forbid();

        var apps = await _db.Applications
            .Where(a => a.JobId == jobId)
            .Include(a => a.Worker)
            .Select(a => new
            {
                a.Id,
                WorkerName = a.Worker!.Name,
                a.Worker.Phone,
                a.Worker.Email,
                a.Worker.Skills,
                a.Status,
                a.CreatedAt
            })
            .ToListAsync();

        return Ok(apps);
    }

    // =================================================================
    // Status transitions
    // =================================================================

    /// <summary>
    /// PUT /api/applications/5/status  body: { "status": "accepted" }
    ///
    /// Permitted moves are declared on JobApplication.AllowedNext:
    ///   pending     → shortlisted | accepted | rejected
    ///   shortlisted → accepted | rejected
    ///   accepted    → completed | rejected
    ///   completed / rejected are terminal
    ///
    /// Marking work completed raises the payment record for the job inside the
    /// same database transaction, so a status change can never be saved without
    /// its payment, or a payment without its status change.
    /// </summary>
    [HttpPut("{id:int}/status")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<ActionResult> UpdateStatus(int id, [FromBody] StatusDto dto)
    {
        var target = (dto.Status ?? "").Trim().ToLowerInvariant();

        var known = new[] { "pending", "shortlisted", "accepted", "rejected", "completed" };
        if (!known.Contains(target))
            return BadRequest(new { message = "Invalid status." });

        var app = await _db.Applications
            .Include(a => a.Job)
            .Include(a => a.Worker)
            .FirstOrDefaultAsync(a => a.Id == id);

        if (app is null) return NotFound(new { message = "Application not found." });

        // Only the employer who owns the job (or an administrator) may decide.
        if (app.Job!.EmployerId != CurrentUserId && !this.User.IsInRole("admin"))
            return Forbid();

        if (app.Status == target)
            return BadRequest(new { message = $"This application is already {target}." });

        if (!JobApplication.CanMove(app.Status, target))
        {
            var reason = app.Status switch
            {
                "completed" => "Completed work cannot be changed.",
                "rejected"  => "A rejected application cannot be changed.",
                _ when target == "completed" =>
                    "A worker must be hired before their work can be verified as completed.",
                _ => $"An application cannot move from {app.Status} to {target}."
            };
            return BadRequest(new { message = reason });
        }

        // Do not let an employer hire more workers than the posting asked for.
        if (target == "accepted")
        {
            var hired = await _db.Applications
                .CountAsync(a => a.JobId == app.JobId && (a.Status == "accepted" || a.Status == "completed"));

            if (hired >= app.Job.WorkersNeeded)
                return BadRequest(new { message = "This job has already hired all the workers it needs." });
        }

        await using var tx = await _db.Database.BeginTransactionAsync();
        try
        {
            var previous = app.Status;
            app.Status = target;
            var now = DateTime.UtcNow;

            switch (target)
            {
                case "shortlisted": app.ShortlistedAt = now; break;
                case "accepted":    app.AcceptedAt    = now; break;
                case "rejected":    app.RejectedAt    = now; break;
                case "completed":   app.CompletedAt   = now; break;
            }

            if (target == "completed")
            {
                // Total the work actually recorded for this assignment. If the
                // employer never logged individual days, fall back to one unit
                // at the agreed rate so the worker is still owed something.
                // Only approved days count. A day the worker submitted and the
                // employer has not accepted must not inflate the amount owed.
                var records = await _db.WorkRecords
                    .Where(w => w.ApplicationId == app.Id && w.Status == "approved")
                    .ToListAsync();

                var units = records.Count > 0 ? records.Sum(w => w.Units) : 1m;
                var rate = app.Job.Pay;
                var total = decimal.Round(rate * units, 2, MidpointRounding.AwayFromZero);

                // One payment per application — the unique index backs this up.
                var payment = await _db.Payments
                    .FirstOrDefaultAsync(p => p.ApplicationId == app.Id);

                if (payment is null)
                {
                    payment = new Payment
                    {
                        JobId = app.JobId,
                        WorkerId = app.WorkerId,
                        ApplicationId = app.Id,
                        AgreedRate = rate,
                        RateUnit = app.Job.Per,
                        UnitsWorked = units,
                        Amount = total,
                        AmountPaid = 0m,
                        Status = "pending"
                    };
                    _db.Payments.Add(payment);
                    await _db.SaveChangesAsync();   // assigns payment.Id

                    _db.PaymentAudits.Add(new PaymentAudit
                    {
                        PaymentId = payment.Id,
                        Action = "created",
                        FromStatus = "",
                        ToStatus = "pending",
                        AmountAtChange = total,
                        ActorUserId = CurrentUserId,
                        ActorRole = this.User.FindFirstValue(ClaimTypes.Role) ?? "",
                        Note = $"Raised automatically when work on \"{app.Job.Title}\" was verified " +
                               $"({units:0.##} {app.Job.Per}(s) at {rate:0.00})."
                    });
                }
            }

            var headline = target switch
            {
                "shortlisted" => "You have been shortlisted",
                "accepted"    => "You have been hired",
                "rejected"    => "Application not successful",
                "completed"   => "Work verified",
                _             => "Application updated"
            };

            var detail = target switch
            {
                "shortlisted" => $"Your application for \"{app.Job.Title}\" has been shortlisted.",
                "accepted"    => $"You were selected for \"{app.Job.Title}\". The employer will contact you.",
                "rejected"    => $"Your application for \"{app.Job.Title}\" was not successful this time.",
                "completed"   => $"Your work on \"{app.Job.Title}\" was verified and your payment record has been raised.",
                _             => $"Your application for \"{app.Job.Title}\" is now {target}."
            };

            _notify.Raise(app.WorkerId, target, headline, detail);

            await _db.SaveChangesAsync();
            await tx.CommitAsync();

            // Tell the worker by email as well. Sent only once the change has
            // been committed, so nobody is emailed about a decision that was
            // rolled back.
            await SendStatusEmailAsync(app, target);

            return Ok(new { message = "Status updated.", from = previous, to = target });
        }
        catch
        {
            await tx.RollbackAsync();
            throw;
        }
    }

    /// <summary>
    /// Emails the worker when they are shortlisted, hired or declined, or when
    /// their work is verified. Never throws.
    /// </summary>
    private async Task SendStatusEmailAsync(JobApplication app, string status)
    {
        try
        {
            var worker = app.Worker;
            var job = app.Job;
            if (worker is null || job is null || !worker.IsActive) return;

            var employerId = job.EmployerId;
            var employer = await _db.Users.AsNoTracking()
                .FirstOrDefaultAsync(u => u.Id == employerId);

            _email.Enqueue(EmailTemplates.ApplicationStatus(worker, job, employer, status));
        }
        catch
        {
            // The status change and the in-app notification are already saved.
        }
    }

    // =================================================================
    // Work records — the daily wage tracking the proposal asks for
    // =================================================================

    /// <summary>
    /// POST /api/applications/5/work
    /// Records one day, shift or block of hours worked against an assignment.
    ///
    /// Open to any signed-in user, because both sides use it: the employer who
    /// owns the job records a day directly, and the hired worker submits one
    /// for approval. The check just below refuses everybody else.
    /// (A role list on this action used to exclude workers, so a worker's
    /// "Record a Work Day" was rejected before that check was ever reached.)
    /// </summary>
    [HttpPost("{id:int}/work")]
    public async Task<ActionResult> AddWorkRecord(int id, [FromBody] WorkRecordCreateDto dto)
    {
        var app = await _db.Applications
            .Include(a => a.Job)
            .Include(a => a.Worker)
            .FirstOrDefaultAsync(a => a.Id == id);

        if (app is null) return NotFound(new { message = "Application not found." });

        // Either side of the assignment may add a day: the employer records it
        // directly, the worker submits it for approval. Nobody else can.
        var isEmployer = app.Job!.EmployerId == CurrentUserId || this.User.IsInRole("admin");
        var isTheWorker = app.WorkerId == CurrentUserId;
        if (!isEmployer && !isTheWorker) return Forbid();

        if (app.Status is not ("accepted" or "completed"))
            return BadRequest(new { message = "Work can only be recorded for a worker who has been hired." });

        // Once the job is completed the payment has already been calculated from
        // the days recorded so far. Adding another day has to either correct that
        // total or be refused — silently leaving the payment behind would mean
        // the worker is owed for work the system does not count.
        Payment? settledPayment = null;
        if (app.Status == "completed")
        {
            settledPayment = await _db.Payments.FirstOrDefaultAsync(p => p.ApplicationId == app.Id);

            if (settledPayment is not null && settledPayment.AmountPaid > 0)
                return BadRequest(new
                {
                    message = "Payment for this job has already started, so the work record cannot " +
                              "be changed. Ask the employer to record a separate payment for any " +
                              "extra work, or raise a dispute on the existing payment."
                });
        }

        if (dto.Units <= 0 || dto.Units > 24)
            return BadRequest(new { message = "Units worked must be between 0 and 24." });

        var workDate = dto.WorkDate?.Date ?? DateTime.UtcNow.Date;
        if (workDate > DateTime.UtcNow.Date)
            return BadRequest(new { message = "Work cannot be recorded for a future date." });

        var duplicate = await _db.WorkRecords
            .AnyAsync(w => w.ApplicationId == id && w.WorkDate == workDate);
        if (duplicate)
            return Conflict(new { message = "Work has already been recorded for that date." });

        var rate = app.Job.Pay;
        var units = decimal.Round(dto.Units, 2, MidpointRounding.AwayFromZero);

        // A day the employer enters is approved on the spot. A day the worker
        // submits waits for the employer to approve it, and does not count
        // towards the amount owed until they do.
        var approved = isEmployer;

        _db.WorkRecords.Add(new WorkRecord
        {
            JobId = app.JobId,
            WorkerId = app.WorkerId,
            ApplicationId = app.Id,
            WorkDate = workDate,
            Units = units,
            Unit = app.Job.Per,
            RateApplied = rate,
            LineTotal = decimal.Round(rate * units, 2, MidpointRounding.AwayFromZero),
            Notes = (dto.Notes ?? "").Trim(),
            Status = approved ? "approved" : "pending",
            SubmittedByUserId = CurrentUserId,
            Verified = approved,
            VerifiedAt = approved ? DateTime.UtcNow : null
        });

        await _db.SaveChangesAsync();

        if (!approved)
        {
            _notify.Raise(app.Job.EmployerId, "work", "Work day submitted for approval",
                $"{app.Worker?.Name ?? "A worker"} submitted {units:0.##} {app.Job.Per}(s) " +
                $"on {workDate:dd MMM yyyy} for \"{app.Job.Title}\". Approve it to include it in their payment.");
            await _db.SaveChangesAsync();

            return Ok(new
            {
                message = "Submitted. The employer will review it and add it to your payment once approved.",
                status = "pending"
            });
        }

        // The job was already completed, so the payment that was raised from the
        // earlier records is now out of date. Recalculate it.
        if (settledPayment is not null)
        {
            var recalculated = await RecalculatePaymentAsync(settledPayment, app);
            return Ok(new
            {
                message = $"Work recorded, and the payment was updated to {recalculated:0.00}.",
                status = "approved",
                amount = recalculated
            });
        }

        return Ok(new { message = "Work recorded.", status = "approved" });
    }

    /// <summary>
    /// PUT /api/applications/work/5  body: { "approve": true, "note": "..." }
    ///
    /// The employer accepts or rejects a day the worker submitted. Approving it
    /// adds it to what the worker is owed; if the job has already been marked
    /// complete the payment is recalculated so the total stays correct.
    /// </summary>
    [HttpPut("work/{recordId:int}")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<ActionResult> DecideWorkRecord(int recordId, [FromBody] WorkDecisionDto dto)
    {
        var record = await _db.WorkRecords
            .Include(w => w.Job)
            .Include(w => w.Application)
            .FirstOrDefaultAsync(w => w.Id == recordId);

        if (record is null) return NotFound(new { message = "Work record not found." });
        if (record.Job!.EmployerId != CurrentUserId && !this.User.IsInRole("admin")) return Forbid();

        if (record.Status != "pending")
            return BadRequest(new { message = "That work record has already been decided." });

        var app = record.Application!;
        var payment = await _db.Payments.FirstOrDefaultAsync(p => p.ApplicationId == app.Id);

        if (dto.Approve && payment is not null && payment.AmountPaid > 0)
            return BadRequest(new
            {
                message = "Payment for this job has already started, so extra work cannot be " +
                          "added to it. Record a separate payment for the additional work."
            });

        record.Status = dto.Approve ? "approved" : "rejected";
        record.Verified = dto.Approve;
        record.VerifiedAt = dto.Approve ? DateTime.UtcNow : null;
        record.DecisionNote = (dto.Note ?? "").Trim();

        await _db.SaveChangesAsync();

        decimal? newTotal = null;
        if (dto.Approve && payment is not null)
            newTotal = await RecalculatePaymentAsync(payment, app);

        _notify.Raise(record.WorkerId, "work",
            dto.Approve ? "Work day approved" : "Work day not approved",
            dto.Approve
                ? $"Your {record.Units:0.##} {record.Unit}(s) on {record.WorkDate:dd MMM yyyy} " +
                  $"for \"{record.Job.Title}\" was approved."
                : $"Your {record.Units:0.##} {record.Unit}(s) on {record.WorkDate:dd MMM yyyy} " +
                  $"for \"{record.Job.Title}\" was not approved." +
                  (string.IsNullOrWhiteSpace(record.DecisionNote) ? "" : $" Reason: {record.DecisionNote}"));

        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = dto.Approve ? "Work approved." : "Work rejected.",
            status = record.Status,
            amount = newTotal
        });
    }

    /// <summary>
    /// Re-derives a payment from the approved work records behind it. Used when
    /// work is added or approved after the job was marked complete. Only ever
    /// called while nothing has been paid, so no settled record is rewritten,
    /// and the change is written to the audit trail.
    /// </summary>
    private async Task<decimal> RecalculatePaymentAsync(Payment payment, JobApplication app)
    {
        var approvedUnits = await _db.WorkRecords
            .Where(w => w.ApplicationId == app.Id && w.Status == "approved")
            .SumAsync(w => (decimal?)w.Units) ?? 0m;

        if (approvedUnits <= 0) approvedUnits = 1m;

        var previous = payment.Amount;
        var rate = payment.AgreedRate > 0 ? payment.AgreedRate : app.Job!.Pay;
        var total = decimal.Round(rate * approvedUnits, 2, MidpointRounding.AwayFromZero);

        if (total == previous) return total;

        payment.UnitsWorked = approvedUnits;
        payment.Amount = total;

        _db.PaymentAudits.Add(new PaymentAudit
        {
            PaymentId = payment.Id,
            Action = "recalculated",
            FromStatus = payment.Status,
            ToStatus = payment.Status,
            AmountAtChange = total,
            ActorUserId = CurrentUserId,
            ActorRole = this.User.FindFirstValue(ClaimTypes.Role) ?? "",
            Note = $"Work record changed after completion: amount updated from {previous:0.00} " +
                   $"to {total:0.00} ({approvedUnits:0.##} {payment.RateUnit}(s) at {rate:0.00})."
        });

        _notify.Raise(payment.WorkerId, "payment", "Payment amount updated",
            $"The amount owed for \"{app.Job?.Title}\" changed from Rs. {previous:N2} to Rs. {total:N2} " +
            "after the work record was updated.");

        await _db.SaveChangesAsync();
        return total;
    }

    /// <summary>GET /api/applications/5/work — the work log for one assignment.</summary>
    [HttpGet("{id:int}/work")]
    public async Task<ActionResult> WorkRecords(int id)
    {
        var app = await _db.Applications
            .Include(a => a.Job)
            .FirstOrDefaultAsync(a => a.Id == id);

        if (app is null) return NotFound(new { message = "Application not found." });

        // Visible to the worker it belongs to, the employer who owns the job, or an admin.
        var me = CurrentUserId;
        if (app.WorkerId != me && app.Job!.EmployerId != me && !this.User.IsInRole("admin"))
            return Forbid();

        var records = await _db.WorkRecords
            .Where(w => w.ApplicationId == id)
            .OrderBy(w => w.WorkDate)
            .Select(w => new WorkRecordDto
            {
                Id = w.Id,
                WorkDate = w.WorkDate,
                Units = w.Units,
                Unit = w.Unit,
                RateApplied = w.RateApplied,
                LineTotal = w.LineTotal,
                Notes = w.Notes,
                Verified = w.Verified,
                Status = w.Status,
                DecisionNote = w.DecisionNote,
                SubmittedByWorker = w.SubmittedByUserId == w.WorkerId
            })
            .ToListAsync();

        // Only approved days count towards what is owed; pending ones are
        // reported separately so both sides can see what is still waiting.
        var approved = records.Where(r => r.Status == "approved").ToList();

        return Ok(new
        {
            applicationId = id,
            jobTitle = app.Job!.Title,
            rate = app.Job.Pay,
            unit = app.Job.Per,
            totalUnits = approved.Sum(r => r.Units),
            totalEarned = approved.Sum(r => r.LineTotal),
            pendingUnits = records.Where(r => r.Status == "pending").Sum(r => r.Units),
            pendingCount = records.Count(r => r.Status == "pending"),
            records
        });
    }
}
