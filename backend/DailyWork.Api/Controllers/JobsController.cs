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
[Route("api/jobs")]
public class JobsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;
    private readonly RecommendationService _recommender;
    private readonly EmailQueue _email;

    public JobsController(AppDbContext db, NotificationService notify, RecommendationService recommender,
                          EmailQueue email)
    {
        _db = db;
        _notify = notify;
        _recommender = recommender;
        _email = email;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    // =================================================================
    // Search
    // =================================================================

    /// <summary>
    /// GET /api/jobs
    ///   ?search=      keyword in title, description, category or employer
    ///   &amp;category=    exact sector
    ///   &amp;location=    town, partial match
    ///   &amp;district=    district, exact
    ///   &amp;minPay=      lowest daily wage
    ///   &amp;maxPay=      highest daily wage
    ///   &amp;skills=      comma separated; matches required skills
    ///   &amp;urgentOnly=  true to show only urgent postings
    ///   &amp;availableOnly=true to hide postings that already hired everyone
    ///   &amp;verifiedOnly=true to show only verified employers
    ///   &amp;sort=        relevance | newest | wage_high | wage_low
    ///   &amp;page= &amp;pageSize=
    /// </summary>
    [HttpGet]
    public async Task<ActionResult> GetJobs([FromQuery] JobSearchQuery q)
    {
        // ---- validate the inputs rather than trusting them ----
        if (q.MinPay is < 0) return BadRequest(new { message = "Minimum wage cannot be negative." });
        if (q.MaxPay is < 0) return BadRequest(new { message = "Maximum wage cannot be negative." });

        if (q.MinPay.HasValue && q.MaxPay.HasValue && q.MinPay > q.MaxPay)
            return BadRequest(new { message = "The minimum wage cannot be higher than the maximum." });

        var page = q.Page < 1 ? 1 : q.Page;
        var pageSize = q.PageSize is < 1 or > 100 ? 20 : q.PageSize;

        var sort = (q.Sort ?? "relevance").Trim().ToLowerInvariant();
        var validSorts = new[] { "relevance", "newest", "wage_high", "wage_low" };
        if (!validSorts.Contains(sort)) sort = "relevance";

        var query = _db.Jobs
            .AsNoTracking()
            .Include(j => j.Employer)
            .Include(j => j.Applications)
            .Where(j => j.Status == "open")
            .AsQueryable();

        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var s = q.Search.Trim().ToLower();
            query = query.Where(j =>
                j.Title.ToLower().Contains(s) ||
                j.Category.ToLower().Contains(s) ||
                j.Description.ToLower().Contains(s) ||
                j.RequiredSkills.ToLower().Contains(s) ||
                j.Employer!.Name.ToLower().Contains(s));
        }

        if (!string.IsNullOrWhiteSpace(q.Category))
            query = query.Where(j => j.Category == q.Category.Trim());

        if (!string.IsNullOrWhiteSpace(q.Location))
        {
            var loc = q.Location.Trim().ToLower();
            query = query.Where(j => j.Location.ToLower().Contains(loc));
        }

        if (!string.IsNullOrWhiteSpace(q.District))
        {
            var d = q.District.Trim().ToLower();
            query = query.Where(j => j.District.ToLower() == d);
        }

        if (q.MinPay.HasValue) query = query.Where(j => j.Pay >= q.MinPay.Value);
        if (q.MaxPay.HasValue) query = query.Where(j => j.Pay <= q.MaxPay.Value);

        if (q.UrgentOnly == true) query = query.Where(j => j.Urgent);

        if (q.VerifiedOnly == true)
            query = query.Where(j => j.Employer!.VerificationStatus == "verified");

        // Skills filter: any one of the listed skills appearing in the posting.
        var wantedSkills = (q.Skills ?? "")
            .Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(s => s.Trim().ToLower())
            .Where(s => s.Length > 1)
            .ToList();

        foreach (var skill in wantedSkills)
        {
            var needle = skill;   // captured per iteration for the expression tree
            query = query.Where(j =>
                j.RequiredSkills.ToLower().Contains(needle) ||
                j.Title.ToLower().Contains(needle) ||
                j.Category.ToLower().Contains(needle));
        }

        query = sort switch
        {
            "newest"    => query.OrderByDescending(j => j.CreatedAt),
            "wage_high" => query.OrderByDescending(j => j.Pay).ThenByDescending(j => j.CreatedAt),
            "wage_low"  => query.OrderBy(j => j.Pay).ThenByDescending(j => j.CreatedAt),
            _           => query.OrderByDescending(j => j.Urgent).ThenByDescending(j => j.CreatedAt)
        };

        var all = await query.ToListAsync();

        // Hide postings that have already hired everyone they need.
        if (q.AvailableOnly == true)
            all = all.Where(j => j.Applications.Count(a => a.Status is "accepted" or "completed")
                                 < j.WorkersNeeded).ToList();

        var total = all.Count;
        var slice = all.Skip((page - 1) * pageSize).Take(pageSize).Select(ToDto).ToList();

        return Ok(new
        {
            total,
            page,
            pageSize,
            totalPages = (int)Math.Ceiling(total / (double)pageSize),
            sort,
            jobs = slice
        });
    }

    /// <summary>GET /api/jobs/5 — everything needed for the job details page.</summary>
    [HttpGet("{id:int}")]
    public async Task<ActionResult> GetJob(int id)
    {
        var j = await _db.Jobs
            .AsNoTracking()
            .Include(x => x.Employer)
            .Include(x => x.Applications)
            .FirstOrDefaultAsync(x => x.Id == id);

        if (j is null) return NotFound(new { message = "Job not found." });

        var dto = ToDto(j);

        // The employer's public reputation, so a worker can judge the posting.
        var employerStars = await _db.Ratings
            .Where(r => r.SubjectId == j.EmployerId)
            .Select(r => r.Stars)
            .ToListAsync();

        var jobsPosted = await _db.Jobs.CountAsync(x => x.EmployerId == j.EmployerId);

        // Whether the signed-in worker has already applied.
        bool alreadyApplied = false;
        if (this.User.Identity?.IsAuthenticated == true &&
            int.TryParse(this.User.FindFirstValue(ClaimTypes.NameIdentifier), out var uid))
        {
            alreadyApplied = await _db.Applications.AnyAsync(a => a.JobId == id && a.WorkerId == uid);
        }

        return Ok(new
        {
            job = dto,
            employer = new
            {
                id = j.EmployerId,
                name = j.Employer?.Name ?? "",
                verified = j.Employer is { VerificationStatus: "verified" },
                organizationName = j.Employer?.OrganizationName ?? "",
                location = j.Employer?.Location ?? "",
                memberSince = j.Employer?.CreatedAt,
                jobsPosted,
                rating = employerStars.Count > 0 ? Math.Round(employerStars.Average(), 1) : 0,
                ratingCount = employerStars.Count
            },
            alreadyApplied
        });
    }

    // =================================================================
    // Posting and editing
    // =================================================================

    /// <summary>POST /api/jobs — employers and organizations only.</summary>
    [Authorize(Roles = "employer,organization,admin")]
    [HttpPost]
    public async Task<ActionResult> CreateJob([FromBody] JobCreateDto dto)
    {
        var problem = ValidateJob(dto);
        if (problem is not null) return BadRequest(new { message = problem });

        var job = new Job
        {
            Title = dto.Title.Trim(),
            Category = dto.Category.Trim(),
            Location = dto.Location.Trim(),
            District = (dto.District ?? dto.Location).Trim(),
            Description = (dto.Description ?? "").Trim(),
            RequiredSkills = (dto.RequiredSkills ?? "").Trim(),
            Pay = decimal.Round(dto.Pay, 2, MidpointRounding.AwayFromZero),
            Per = string.IsNullOrWhiteSpace(dto.Per) ? "day" : dto.Per.Trim().ToLowerInvariant(),
            Urgent = dto.Urgent,
            WorkersNeeded = dto.WorkersNeeded < 1 ? 1 : dto.WorkersNeeded,
            ExpectedUnits = dto.ExpectedUnits < 1 ? 1 : dto.ExpectedUnits,
            StartDate = dto.StartDate,
            EndDate = dto.EndDate,
            ProjectId = await ResolveProjectIdAsync(dto.ProjectId),
            EmployerId = CurrentUserId
        };

        _db.Jobs.Add(job);
        await _db.SaveChangesAsync();

        // Tell suitable workers that a job matching their profile has appeared.
        var notified = await NotifyMatchingWorkersAsync(job);

        // Confirm the posting to the employer by email.
        await SendJobPostedEmailAsync(job, notified);

        return CreatedAtAction(nameof(GetJob), new { id = job.Id },
            new { job.Id, message = "Job posted." });
    }

    /// <summary>
    /// PUT /api/jobs/5 — edit a posting.
    /// Only the employer who owns it may change it; the ownership check is what
    /// stops one employer editing another's jobs.
    /// </summary>
    [Authorize(Roles = "employer,organization,admin")]
    [HttpPut("{id:int}")]
    public async Task<ActionResult> UpdateJob(int id, [FromBody] JobCreateDto dto)
    {
        var job = await _db.Jobs.Include(j => j.Applications).FirstOrDefaultAsync(j => j.Id == id);
        if (job is null) return NotFound(new { message = "Job not found." });

        if (job.EmployerId != CurrentUserId && !this.User.IsInRole("admin"))
            return Forbid();

        if (job.Status == "closed")
            return BadRequest(new { message = "A closed job cannot be edited." });

        var problem = ValidateJob(dto);
        if (problem is not null) return BadRequest(new { message = problem });

        var hired = job.Applications.Count(a => a.Status is "accepted" or "completed");
        if (dto.WorkersNeeded < hired)
            return BadRequest(new
            {
                message = $"You have already hired {hired} worker(s), so the number required cannot be lower than that."
            });

        // Changing the wage after hiring would alter what was agreed.
        var newPay = decimal.Round(dto.Pay, 2, MidpointRounding.AwayFromZero);
        if (hired > 0 && newPay != job.Pay)
            return BadRequest(new
            {
                message = "The wage cannot be changed after a worker has been hired for this job."
            });

        job.Title = dto.Title.Trim();
        job.Category = dto.Category.Trim();
        job.Location = dto.Location.Trim();
        job.District = (dto.District ?? dto.Location).Trim();
        job.Description = (dto.Description ?? "").Trim();
        job.RequiredSkills = (dto.RequiredSkills ?? "").Trim();
        job.Pay = newPay;
        job.Per = string.IsNullOrWhiteSpace(dto.Per) ? job.Per : dto.Per.Trim().ToLowerInvariant();
        job.Urgent = dto.Urgent;
        job.WorkersNeeded = dto.WorkersNeeded < 1 ? 1 : dto.WorkersNeeded;
        job.ExpectedUnits = dto.ExpectedUnits < 1 ? 1 : dto.ExpectedUnits;
        job.StartDate = dto.StartDate;
        job.EndDate = dto.EndDate;
        job.ProjectId = await ResolveProjectIdAsync(dto.ProjectId);
        job.UpdatedAt = DateTime.UtcNow;

        // Anyone waiting on a decision should know the posting changed.
        var waiting = job.Applications
            .Where(a => a.Status is "pending" or "shortlisted")
            .Select(a => a.WorkerId)
            .Distinct();

        foreach (var workerId in waiting)
            _notify.Raise(workerId, "system", "A job you applied for was updated",
                $"\"{job.Title}\" has been updated by the employer.");

        await _db.SaveChangesAsync();
        return Ok(new { message = "Job updated." });
    }

    /// <summary>DELETE /api/jobs/5 — closes a job the caller owns.</summary>
    [Authorize]
    [HttpDelete("{id:int}")]
    public async Task<ActionResult> CloseJob(int id)
    {
        var job = await _db.Jobs.Include(j => j.Applications).FirstOrDefaultAsync(j => j.Id == id);
        if (job is null) return NotFound(new { message = "Job not found." });

        if (job.EmployerId != CurrentUserId && !this.User.IsInRole("admin"))
            return Forbid();

        if (job.Status == "closed")
            return BadRequest(new { message = "This job is already closed." });

        job.Status = "closed";
        job.UpdatedAt = DateTime.UtcNow;

        foreach (var workerId in job.Applications
                     .Where(a => a.Status is "pending" or "shortlisted")
                     .Select(a => a.WorkerId).Distinct())
        {
            _notify.Raise(workerId, "system", "A job you applied for has closed",
                $"\"{job.Title}\" is no longer accepting applications.");
        }

        await _db.SaveChangesAsync();
        return Ok(new { message = "Job closed." });
    }

    // =================================================================
    // Helpers
    // =================================================================

    /// <summary>
    /// Accepts a project id only when the project really belongs to the caller.
    /// Anything else — a missing project, or one owned by another organization —
    /// is treated as "no project" rather than an error, so a posting is never
    /// silently filed under somebody else's work.
    /// </summary>
    private async Task<int?> ResolveProjectIdAsync(int? projectId)
    {
        if (projectId is null or <= 0) return null;

        var owned = await _db.Projects
            .AnyAsync(p => p.Id == projectId && p.OrganizationId == CurrentUserId);

        return owned ? projectId : null;
    }

    private static string? ValidateJob(JobCreateDto dto)
    {
        if (string.IsNullOrWhiteSpace(dto.Title) || dto.Title.Trim().Length < 3)
            return "Please enter a job title of at least 3 characters.";

        if (string.IsNullOrWhiteSpace(dto.Category))
            return "Please choose a category.";

        if (string.IsNullOrWhiteSpace(dto.Location))
            return "Please enter where the work is.";

        if (dto.Pay <= 0)
            return "Please enter the wage amount.";

        if (dto.Pay > 1_000_000)
            return "That wage looks too high. Please check the amount.";

        var units = new[] { "day", "shift", "hour" };
        if (!string.IsNullOrWhiteSpace(dto.Per) && !units.Contains(dto.Per.Trim().ToLowerInvariant()))
            return "Pay unit must be day, shift or hour.";

        if (dto.WorkersNeeded is < 1 or > 500)
            return "Number of workers must be between 1 and 500.";

        if (dto.StartDate.HasValue && dto.EndDate.HasValue && dto.EndDate < dto.StartDate)
            return "The end date cannot be before the start date.";

        if (dto.EndDate.HasValue && dto.EndDate.Value.Date < DateTime.UtcNow.Date)
            return "The end date cannot be in the past.";

        return null;
    }

    /// <summary>
    /// Alerts workers whose profile matches a newly posted job, in the app and
    /// by email. Capped so a single posting cannot flood every worker on the
    /// platform. Returns how many workers were told.
    /// </summary>
    private async Task<int> NotifyMatchingWorkersAsync(Job job)
    {
        try
        {
            var matches = await _recommender.WorkersForJobAsync(job, minScore: 30, take: 25);
            if (matches.Count == 0) return 0;

            foreach (var (workerId, score) in matches)
            {
                _notify.Raise(workerId, "job_match", "New job that matches your profile",
                    $"\"{job.Title}\" in {job.Location} pays Rs. {job.Pay:N0} per {job.Per}. " +
                    $"It matches your skills and area.");
            }

            await _db.SaveChangesAsync();

            await SendJobMatchEmailsAsync(job, matches.Select(m => m.WorkerId).ToList());

            return matches.Count;
        }
        catch
        {
            // A failure to notify must never stop the job being posted.
            return 0;
        }
    }

    /// <summary>Emails the same matching workers the in-app alert went to.</summary>
    private async Task SendJobMatchEmailsAsync(Job job, List<int> workerIds)
    {
        try
        {
            var employerId = job.EmployerId;

            var employerName = await _db.Users.AsNoTracking()
                .Where(u => u.Id == employerId)
                .Select(u => u.Name)
                .FirstOrDefaultAsync() ?? "An employer";

            var workers = await _db.Users.AsNoTracking()
                .Where(u => workerIds.Contains(u.Id) && u.IsActive)
                .Select(u => new { u.Name, u.Email })
                .ToListAsync();

            foreach (var worker in workers)
                _email.Enqueue(EmailTemplates.JobMatch(worker.Name, worker.Email, job, employerName));
        }
        catch
        {
            // The in-app alerts are already saved; email is in addition to them.
        }
    }

    /// <summary>Emails the employer a confirmation that their job is live.</summary>
    private async Task SendJobPostedEmailAsync(Job job, int workersNotified)
    {
        try
        {
            var employerId = job.EmployerId;

            var employer = await _db.Users.AsNoTracking()
                .FirstOrDefaultAsync(u => u.Id == employerId);

            if (employer is not null)
                _email.Enqueue(EmailTemplates.JobPosted(employer, job, workersNotified));
        }
        catch
        {
            // The job is already posted; the confirmation email is a courtesy.
        }
    }

    private static JobDto ToDto(Job j) => new()
    {
        Id = j.Id,
        Title = j.Title,
        Category = j.Category,
        Location = j.Location,
        District = j.District,
        Description = j.Description,
        RequiredSkills = j.RequiredSkills,
        Pay = j.Pay,
        Per = j.Per,
        Urgent = j.Urgent,
        Status = j.Status,
        WorkersNeeded = j.WorkersNeeded,
        ExpectedUnits = j.ExpectedUnits,
        StartDate = j.StartDate,
        EndDate = j.EndDate,
        EmployerId = j.EmployerId,
        EmployerName = j.Employer?.Name ?? "",
        EmployerVerified = j.Employer is { VerificationStatus: "verified" },
        Applications = j.Applications?.Count ?? 0,
        PositionsFilled = j.Applications?.Count(a => a.Status is "accepted" or "completed") ?? 0,
        CreatedAt = j.CreatedAt
    };
}
