using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Project management and recruitment tracking for organizations.
///
/// An individual employer posts a job at a time. An organization runs projects
/// — a construction site, a seasonal harvest, a contract — each needing a
/// number of workers across several postings. This groups those postings and
/// answers the questions an organization actually has: how many of the people
/// we need have we hired, which postings are still short, and what has the
/// project cost so far against its budget.
///
/// Restricted to the organization role. Ordinary employers are unaffected.
/// </summary>
[ApiController]
[Route("api/projects")]
[Authorize(Roles = "organization,admin")]
public class ProjectsController : ControllerBase
{
    private readonly AppDbContext _db;

    public ProjectsController(AppDbContext db) => _db = db;

    private int CurrentUserId =>
        int.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier) ?? "0");

    /// <summary>
    /// GET /api/projects — every project this organization owns, each with its
    /// recruitment position worked out from the real applications and payments
    /// behind it.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult> Mine()
    {
        var me = CurrentUserId;

        var projects = await _db.Projects
            .AsNoTracking()
            .Where(p => p.OrganizationId == me)
            .OrderByDescending(p => p.CreatedAt)
            .ToListAsync();

        if (projects.Count == 0)
            return Ok(new { projects = Array.Empty<object>(), summary = EmptySummary() });

        var ids = projects.Select(p => p.Id).ToList();

        // Pull the jobs and their applications once, then work out each
        // project's position in memory rather than querying per project.
        var jobs = await _db.Jobs
            .AsNoTracking()
            .Include(j => j.Applications)
            .Where(j => j.ProjectId != null && ids.Contains(j.ProjectId.Value))
            .ToListAsync();

        var jobIds = jobs.Select(j => j.Id).ToList();

        var payments = await _db.Payments
            .AsNoTracking()
            .Where(p => jobIds.Contains(p.JobId))
            .Select(p => new { p.JobId, p.Amount, p.AmountPaid })
            .ToListAsync();

        var rows = new List<ProjectDto>();

        foreach (var project in projects)
        {
            var projectJobs = jobs.Where(j => j.ProjectId == project.Id).ToList();
            var projectJobIds = projectJobs.Select(j => j.Id).ToHashSet();
            var projectPayments = payments.Where(p => projectJobIds.Contains(p.JobId)).ToList();

            var applications = projectJobs.SelectMany(j => j.Applications).ToList();

            var hired = applications.Count(a => a.Status is "accepted" or "completed");
            var completed = applications.Count(a => a.Status == "completed");

            // Positions are counted from the postings themselves, so the figure
            // is real rather than whatever was typed on the project.
            var positionsPosted = projectJobs.Sum(j => j.WorkersNeeded);

            // What the organization said it needs overall. If it was left blank,
            // fall back to the positions actually advertised.
            var required = project.WorkersRequired > 0 ? project.WorkersRequired : positionsPosted;

            var committed = projectPayments.Sum(p => p.Amount);
            var paid = projectPayments.Sum(p => p.AmountPaid);

            rows.Add(new ProjectDto
            {
                Id = project.Id,
                Name = project.Name,
                Description = project.Description,
                Location = project.Location,
                District = project.District,
                Status = project.Status,
                StartDate = project.StartDate,
                EndDate = project.EndDate,
                Budget = project.Budget,
                CreatedAt = project.CreatedAt,

                WorkersRequired = required,
                PositionsPosted = positionsPosted,
                JobsPosted = projectJobs.Count,
                OpenJobs = projectJobs.Count(j => j.Status == "open"),
                Applicants = applications.Count,
                Shortlisted = applications.Count(a => a.Status == "shortlisted"),
                Hired = hired,
                Completed = completed,
                StillNeeded = Math.Max(0, required - hired),
                FillRate = required > 0
                    ? Math.Round(hired * 100.0 / required, 1)
                    : 0,

                Committed = committed,
                Paid = paid,
                Outstanding = committed - paid,
                BudgetUsed = project.Budget > 0
                    ? Math.Round((double)(committed / project.Budget) * 100, 1)
                    : 0,
                OverBudget = project.Budget > 0 && committed > project.Budget,

                Jobs = projectJobs
                    .OrderByDescending(j => j.CreatedAt)
                    .Select(j => new ProjectJobDto
                    {
                        Id = j.Id,
                        Title = j.Title,
                        Status = j.Status,
                        Location = j.Location,
                        Pay = j.Pay,
                        Per = j.Per,
                        WorkersNeeded = j.WorkersNeeded,
                        Applicants = j.Applications.Count,
                        Hired = j.Applications.Count(a => a.Status is "accepted" or "completed")
                    })
                    .ToList()
            });
        }

        return Ok(new
        {
            projects = rows,
            summary = new
            {
                total = rows.Count,
                active = rows.Count(r => r.Status == "active"),
                completed = rows.Count(r => r.Status == "completed"),
                workersRequired = rows.Sum(r => r.WorkersRequired),
                hired = rows.Sum(r => r.Hired),
                stillNeeded = rows.Sum(r => r.StillNeeded),
                committed = rows.Sum(r => r.Committed),
                paid = rows.Sum(r => r.Paid),
                outstanding = rows.Sum(r => r.Outstanding)
            }
        });
    }

    private static object EmptySummary() => new
    {
        total = 0, active = 0, completed = 0,
        workersRequired = 0, hired = 0, stillNeeded = 0,
        committed = 0m, paid = 0m, outstanding = 0m
    };

    /// <summary>POST /api/projects — start a new project.</summary>
    [HttpPost]
    public async Task<ActionResult> Create([FromBody] ProjectCreateDto dto)
    {
        var name = (dto.Name ?? "").Trim();
        if (name.Length < 3)
            return BadRequest(new { message = "Give the project a name of at least 3 characters." });

        if (dto.WorkersRequired < 0 || dto.WorkersRequired > 10000)
            return BadRequest(new { message = "The number of workers required is not valid." });

        if (dto.Budget < 0)
            return BadRequest(new { message = "The budget cannot be negative." });

        if (dto.StartDate is not null && dto.EndDate is not null && dto.EndDate < dto.StartDate)
            return BadRequest(new { message = "The end date cannot be before the start date." });

        var project = new Project
        {
            OrganizationId = CurrentUserId,
            Name = name,
            Description = (dto.Description ?? "").Trim(),
            Location = (dto.Location ?? "").Trim(),
            District = (dto.District ?? "").Trim(),
            WorkersRequired = dto.WorkersRequired,
            Budget = dto.Budget,
            StartDate = dto.StartDate,
            EndDate = dto.EndDate,
            Status = NormaliseStatus(dto.Status)
        };

        _db.Projects.Add(project);
        await _db.SaveChangesAsync();

        return Ok(new { message = "Project created.", id = project.Id });
    }

    /// <summary>PUT /api/projects/5 — edit a project.</summary>
    [HttpPut("{id:int}")]
    public async Task<ActionResult> Update(int id, [FromBody] ProjectCreateDto dto)
    {
        var project = await _db.Projects.FirstOrDefaultAsync(p => p.Id == id);
        if (project is null) return NotFound(new { message = "Project not found." });
        if (project.OrganizationId != CurrentUserId && !User.IsInRole("admin")) return Forbid();

        if (!string.IsNullOrWhiteSpace(dto.Name))
        {
            if (dto.Name.Trim().Length < 3)
                return BadRequest(new { message = "Give the project a name of at least 3 characters." });
            project.Name = dto.Name.Trim();
        }

        if (dto.StartDate is not null && dto.EndDate is not null && dto.EndDate < dto.StartDate)
            return BadRequest(new { message = "The end date cannot be before the start date." });

        if (dto.Description is not null) project.Description = dto.Description.Trim();
        if (dto.Location is not null) project.Location = dto.Location.Trim();
        if (dto.District is not null) project.District = dto.District.Trim();
        if (dto.WorkersRequired > 0) project.WorkersRequired = dto.WorkersRequired;
        if (dto.Budget > 0) project.Budget = dto.Budget;
        if (dto.StartDate is not null) project.StartDate = dto.StartDate;
        if (dto.EndDate is not null) project.EndDate = dto.EndDate;
        if (!string.IsNullOrWhiteSpace(dto.Status)) project.Status = NormaliseStatus(dto.Status);

        project.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync();

        return Ok(new { message = "Project updated." });
    }

    /// <summary>
    /// DELETE /api/projects/5 — removes the project. Any jobs posted under it
    /// are kept and simply stop belonging to a project, so no application,
    /// payment or rating history is lost.
    /// </summary>
    [HttpDelete("{id:int}")]
    public async Task<ActionResult> Delete(int id)
    {
        var project = await _db.Projects.FirstOrDefaultAsync(p => p.Id == id);
        if (project is null) return NotFound(new { message = "Project not found." });
        if (project.OrganizationId != CurrentUserId && !User.IsInRole("admin")) return Forbid();

        var attached = await _db.Jobs.Where(j => j.ProjectId == id).ToListAsync();
        foreach (var job in attached) job.ProjectId = null;

        _db.Projects.Remove(project);
        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = attached.Count > 0
                ? $"Project removed. {attached.Count} job posting(s) were kept and no longer belong to a project."
                : "Project removed."
        });
    }

    private static string NormaliseStatus(string? status)
    {
        var s = (status ?? "").Trim().ToLowerInvariant();
        return s is "planning" or "active" or "completed" or "cancelled" ? s : "planning";
    }
}
