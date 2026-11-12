using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Everything an employer or organization needs to run their own hiring:
/// their postings, the people who applied, and the payments they owe.
/// </summary>
[ApiController]
[Route("api/employer")]
[Authorize(Roles = "employer,organization,admin")]
public class EmployerController : ControllerBase
{
    private readonly AppDbContext _db;

    public EmployerController(AppDbContext db) => _db = db;

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/employer/stats — headline numbers for the dashboard.</summary>
    [HttpGet("stats")]
    public async Task<ActionResult> Stats()
    {
        var me = CurrentUserId;
        var jobIds = await _db.Jobs.Where(j => j.EmployerId == me).Select(j => j.Id).ToListAsync();

        var payments = await _db.Payments
            .Where(p => jobIds.Contains(p.JobId))
            .Select(p => new { p.Amount, p.AmountPaid })
            .ToListAsync();

        var apps = await _db.Applications
            .Where(a => jobIds.Contains(a.JobId))
            .Select(a => a.Status)
            .ToListAsync();

        var user = await _db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == me);

        return Ok(new
        {
            myJobs        = jobIds.Count,
            openJobs      = await _db.Jobs.CountAsync(j => j.EmployerId == me && j.Status == "open"),
            applicants    = apps.Count,
            pendingReview = apps.Count(s => s == "pending"),
            shortlisted   = apps.Count(s => s == "shortlisted"),
            hired         = apps.Count(s => s == "accepted"),
            completed     = apps.Count(s => s == "completed"),
            amountOwed    = payments.Sum(p => p.Amount - p.AmountPaid),
            amountPaid    = payments.Sum(p => p.AmountPaid),
            verificationStatus = user?.VerificationStatus ?? "unverified",
            isVerified    = user?.VerificationStatus == "verified"
        });
    }

    /// <summary>GET /api/employer/jobs — this employer's own postings.</summary>
    [HttpGet("jobs")]
    public async Task<ActionResult> MyJobs()
    {
        var me = CurrentUserId;

        var jobs = await _db.Jobs
            .Where(j => j.EmployerId == me)
            .Include(j => j.Applications)
            .OrderByDescending(j => j.CreatedAt)
            .Select(j => new
            {
                j.Id, j.Title, j.Category, j.Location, j.District,
                j.Pay, j.Per, j.Urgent, j.Status, j.Description,
                j.RequiredSkills, j.WorkersNeeded, j.ExpectedUnits,
                j.StartDate, j.EndDate,
                Applications = j.Applications.Count,
                Pending = j.Applications.Count(a => a.Status == "pending"),
                Shortlisted = j.Applications.Count(a => a.Status == "shortlisted"),
                Hired = j.Applications.Count(a => a.Status == "accepted"),
                Completed = j.Applications.Count(a => a.Status == "completed"),
                j.CreatedAt, j.UpdatedAt
            })
            .ToListAsync();

        return Ok(jobs);
    }

    /// <summary>GET /api/employer/applicants — everyone who applied, with their record.</summary>
    [HttpGet("applicants")]
    public async Task<ActionResult<IEnumerable<ApplicantDto>>> Applicants([FromQuery] int? jobId)
    {
        var me = CurrentUserId;

        var q = _db.Applications.Where(a => a.Job!.EmployerId == me);
        if (jobId.HasValue) q = q.Where(a => a.JobId == jobId.Value);

        var apps = await q
            .Include(a => a.Job)
            .Include(a => a.Worker)
            .OrderByDescending(a => a.CreatedAt)
            .Select(a => new
            {
                a.Id, a.JobId,
                JobTitle = a.Job!.Title,
                a.WorkerId,
                WorkerName = a.Worker!.Name,
                WorkerPhone = a.Worker.Phone,
                WorkerEmail = a.Worker.Email,
                WorkerSkills = a.Worker.Skills,
                WorkerExperience = a.Worker.Experience,
                WorkerExperienceYears = a.Worker.ExperienceYears,
                WorkerLocation = a.Worker.Location,
                a.Message, a.Status, a.CreatedAt
            })
            .ToListAsync();

        // Ratings and completed counts are gathered separately so the query above
        // stays simple enough for the provider to translate.
        var workerIds = apps.Select(a => a.WorkerId).Distinct().ToList();

        var ratings = await _db.Ratings
            .Where(r => workerIds.Contains(r.SubjectId))
            .Select(r => new { r.SubjectId, r.Stars })
            .ToListAsync();

        var completedCounts = await _db.Applications
            .Where(a => workerIds.Contains(a.WorkerId) && a.Status == "completed")
            .GroupBy(a => a.WorkerId)
            .Select(g => new { WorkerId = g.Key, Count = g.Count() })
            .ToListAsync();

        // Which of these applicants have a CV on file. Only the file name is
        // read; the file itself is fetched when the employer downloads it.
        var cvs = await _db.CvDocuments
            .Where(c => workerIds.Contains(c.UserId))
            .Select(c => new { c.UserId, c.FileName })
            .ToListAsync();

        var result = apps.Select(a =>
        {
            var mine = ratings.Where(r => r.SubjectId == a.WorkerId).Select(r => r.Stars).ToList();
            var cv = cvs.FirstOrDefault(c => c.UserId == a.WorkerId);
            return new ApplicantDto
            {
                Id = a.Id,
                JobId = a.JobId,
                JobTitle = a.JobTitle,
                WorkerId = a.WorkerId,
                WorkerName = a.WorkerName,
                WorkerPhone = a.WorkerPhone,
                WorkerEmail = a.WorkerEmail,
                WorkerSkills = a.WorkerSkills,
                WorkerExperience = a.WorkerExperience,
                WorkerExperienceYears = a.WorkerExperienceYears,
                WorkerLocation = a.WorkerLocation,
                WorkerRating = mine.Count == 0 ? 0 : Math.Round(mine.Average(), 1),
                WorkerJobsCompleted = completedCounts.FirstOrDefault(c => c.WorkerId == a.WorkerId)?.Count ?? 0,
                WorkerHasCv = cv is not null,
                WorkerCvFileName = cv?.FileName ?? "",
                Message = a.Message,
                Status = a.Status,
                CreatedAt = a.CreatedAt
            };
        }).ToList();

        return Ok(result);
    }

    /// <summary>GET /api/employer/payments — what this employer owes and has paid.</summary>
    [HttpGet("payments")]
    public async Task<ActionResult<IEnumerable<EmployerPaymentDto>>> Payments()
    {
        var me = CurrentUserId;

        var payments = await _db.Payments
            .Where(p => p.Job!.EmployerId == me)
            .Include(p => p.Job)
            .Include(p => p.Worker)
            .OrderBy(p => p.Status == "paid")          // outstanding first
            .ThenByDescending(p => p.CreatedAt)
            .Select(p => new EmployerPaymentDto
            {
                Id = p.Id,
                JobId = p.JobId,
                JobTitle = p.Job!.Title,
                WorkerId = p.WorkerId,
                WorkerName = p.Worker!.Name,
                AgreedRate = p.AgreedRate,
                RateUnit = p.RateUnit,
                UnitsWorked = p.UnitsWorked,
                Amount = p.Amount,
                AmountPaid = p.AmountPaid,
                Status = p.Status,
                WorkerConfirmed = p.WorkerConfirmed,
                ConfirmedAmount = p.ConfirmedAmount,
                AwaitingConfirmation = p.AmountPaid - p.ConfirmedAmount,
                PaidAt = p.PaidAt,
                CreatedAt = p.CreatedAt
            })
            .ToListAsync();

        foreach (var p in payments) p.Outstanding = p.Amount - p.AmountPaid;

        return Ok(payments);
    }
}
