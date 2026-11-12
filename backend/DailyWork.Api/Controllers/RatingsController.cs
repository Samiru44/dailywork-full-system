using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Two-way reviews. A review is only accepted when the author and the subject
/// were genuinely the two sides of one completed job, so reputation on the
/// platform always traces back to real work.
/// </summary>
[ApiController]
[Route("api/ratings")]
public class RatingsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;

    public RatingsController(AppDbContext db, NotificationService notify)
    {
        _db = db;
        _notify = notify;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/ratings/user/5 — public reviews for one person.</summary>
    [HttpGet("user/{userId:int}")]
    public async Task<ActionResult<IEnumerable<RatingDto>>> ForUser(int userId)
    {
        var list = await _db.Ratings
            .Where(r => r.SubjectId == userId)
            .Include(r => r.Job)
            .Include(r => r.Author)
            .Include(r => r.Subject)
            .OrderByDescending(r => r.CreatedAt)
            .Select(r => new RatingDto
            {
                Id = r.Id,
                JobId = r.JobId,
                JobTitle = r.Job!.Title,
                AuthorName = r.Author!.Name,
                SubjectName = r.Subject!.Name,
                Stars = r.Stars,
                Comment = r.Comment,
                CreatedAt = r.CreatedAt
            })
            .ToListAsync();

        return Ok(list);
    }

    /// <summary>GET /api/ratings/mine — reviews written about the signed-in user.</summary>
    [Authorize]
    [HttpGet("mine")]
    public async Task<ActionResult<IEnumerable<RatingDto>>> Mine() => await ForUser(CurrentUserId);

    /// <summary>
    /// GET /api/ratings/pending — completed jobs the signed-in user has not yet
    /// reviewed, so the interface can offer the form at the right moment.
    /// </summary>
    [Authorize]
    [HttpGet("pending")]
    public async Task<ActionResult> Pending()
    {
        var me = CurrentUserId;

        // Jobs I completed as the worker → I may review that job's employer.
        var asWorker = await _db.Applications
            .Where(a => a.WorkerId == me && a.Status == "completed")
            .Include(a => a.Job).ThenInclude(j => j!.Employer)
            .Select(a => new
            {
                jobId = a.JobId,
                jobTitle = a.Job!.Title,
                subjectId = a.Job.EmployerId,
                subjectName = a.Job.Employer!.Name,
                subjectRole = "employer"
            })
            .ToListAsync();

        // Jobs I posted where someone completed the work → I may review each worker.
        var asEmployer = await _db.Applications
            .Where(a => a.Status == "completed" && a.Job!.EmployerId == me)
            .Include(a => a.Job)
            .Include(a => a.Worker)
            .Select(a => new
            {
                jobId = a.JobId,
                jobTitle = a.Job!.Title,
                subjectId = a.WorkerId,
                subjectName = a.Worker!.Name,
                subjectRole = "worker"
            })
            .ToListAsync();

        var alreadyRated = await _db.Ratings
            .Where(r => r.AuthorId == me)
            .Select(r => new { r.JobId, r.SubjectId })
            .ToListAsync();

        var pending = asWorker.Concat(asEmployer)
            .Where(x => !alreadyRated.Any(r => r.JobId == x.jobId && r.SubjectId == x.subjectId))
            .ToList();

        return Ok(pending);
    }

    /// <summary>
    /// POST /api/ratings
    ///
    /// The subject is checked against the job, not taken on trust. A worker may
    /// only review the employer who posted the job they completed, and an
    /// employer may only review a worker who actually completed that job — so a
    /// valid author cannot pass an arbitrary user id and rate a stranger.
    /// </summary>
    [Authorize]
    [HttpPost]
    public async Task<ActionResult> Create([FromBody] RatingCreateDto dto)
    {
        if (dto.Stars < 1 || dto.Stars > 5)
            return BadRequest(new { message = "Please give a rating between 1 and 5 stars." });

        var me = CurrentUserId;

        if (dto.SubjectId == me)
            return BadRequest(new { message = "You cannot rate yourself." });

        var job = await _db.Jobs.FindAsync(dto.JobId);
        if (job is null) return NotFound(new { message = "Job not found." });

        var subject = await _db.Users.FindAsync(dto.SubjectId);
        if (subject is null) return NotFound(new { message = "The person you are reviewing was not found." });

        string subjectRole;

        if (job.EmployerId == me)
        {
            // I posted this job, so the subject must be a worker who completed it.
            var workerCompleted = await _db.Applications.AnyAsync(a =>
                a.JobId == dto.JobId &&
                a.WorkerId == dto.SubjectId &&
                a.Status == "completed");

            if (!workerCompleted)
                return BadRequest(new
                {
                    message = "You can only review a worker who completed this job for you."
                });

            subjectRole = "worker";
        }
        else
        {
            // I am not the employer, so I must be a worker who completed this job,
            // and the only person I may review is that job's employer.
            var iCompleted = await _db.Applications.AnyAsync(a =>
                a.JobId == dto.JobId &&
                a.WorkerId == me &&
                a.Status == "completed");

            if (!iCompleted)
                return BadRequest(new
                {
                    message = "You can only review someone after you have completed their job."
                });

            if (dto.SubjectId != job.EmployerId)
                return BadRequest(new
                {
                    message = "You can only review the employer who hired you for this job."
                });

            subjectRole = "employer";
        }

        var duplicate = await _db.Ratings.AnyAsync(r =>
            r.JobId == dto.JobId && r.AuthorId == me && r.SubjectId == dto.SubjectId);

        if (duplicate)
            return Conflict(new { message = "You have already reviewed this job." });

        _db.Ratings.Add(new Rating
        {
            JobId = dto.JobId,
            AuthorId = me,
            SubjectId = dto.SubjectId,
            Stars = dto.Stars,
            Comment = (dto.Comment ?? "").Trim(),
            SubjectRole = subjectRole
        });

        var author = await _db.Users.FindAsync(me);
        _notify.Raise(dto.SubjectId, "rating", "New review received",
            $"{author?.Name} rated you {dto.Stars} star{(dto.Stars == 1 ? "" : "s")} for \"{job.Title}\".");

        await _db.SaveChangesAsync();
        return Ok(new { message = "Thank you, your review has been saved." });
    }
}
