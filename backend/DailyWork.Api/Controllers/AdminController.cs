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
/// Every endpoint here requires a JWT whose role claim is "admin".
/// This attribute is the real protection — hiding the Admin button in the
/// browser only tidies the interface, it does not secure anything.
/// </summary>
[ApiController]
[Route("api/admin")]
[Authorize(Roles = "admin")]
public class AdminController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;

    public AdminController(AppDbContext db, NotificationService notify)
    {
        _db = db;
        _notify = notify;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    // =================================================================
    // Overview
    // =================================================================

    /// <summary>GET /api/admin/stats</summary>
    [HttpGet("stats")]
    public async Task<ActionResult> Stats()
    {
        var paidAmounts = await _db.Payments.Select(p => p.AmountPaid).ToListAsync();
        var owedAmounts = await _db.Payments
            .Where(p => p.Status != "paid")
            .Select(p => new { p.Amount, p.AmountPaid })
            .ToListAsync();

        return Ok(new
        {
            totalUsers    = await _db.Users.CountAsync(),
            activeUsers   = await _db.Users.CountAsync(u => u.IsActive),
            workers       = await _db.Users.CountAsync(u => u.Role == "worker"),
            employers     = await _db.Users.CountAsync(u => u.Role == "employer"),
            organizations = await _db.Users.CountAsync(u => u.Role == "organization"),
            admins        = await _db.Users.CountAsync(u => u.Role == "admin"),
            totalJobs     = await _db.Jobs.CountAsync(),
            openJobs      = await _db.Jobs.CountAsync(j => j.Status == "open"),
            applications  = await _db.Applications.CountAsync(),
            completedJobs = await _db.Applications.CountAsync(a => a.Status == "completed"),
            payments      = await _db.Payments.CountAsync(),
            paidAmount    = paidAmounts.Sum(),
            outstanding   = owedAmounts.Sum(p => p.Amount - p.AmountPaid),
            pendingVerifications = await _db.Users.CountAsync(u => u.VerificationStatus == "pending"),
            newMessages   = await _db.ContactMessages.CountAsync(m => m.Status == "new")
        });
    }

    // =================================================================
    // Users
    // =================================================================

    /// <summary>GET /api/admin/users</summary>
    [HttpGet("users")]
    public async Task<ActionResult> Users()
    {
        var users = await _db.Users
            .OrderByDescending(u => u.CreatedAt)
            .Select(u => new
            {
                u.Id, u.Name, u.Email, u.Phone, u.Role, u.CreatedAt,
                u.IsActive, u.VerificationStatus, u.District, u.Location
            })
            .ToListAsync();

        return Ok(users);
    }

    /// <summary>
    /// PUT /api/admin/users/5/role  body: { "role": "employer" }
    /// Changing a role bumps the security stamp, which immediately invalidates
    /// any token the user is still holding under the old role.
    /// </summary>
    [HttpPut("users/{id:int}/role")]
    public async Task<ActionResult> ChangeRole(int id, [FromBody] RoleDto dto)
    {
        var allowed = new[] { "worker", "employer", "organization", "admin" };
        if (!allowed.Contains(dto.Role))
            return BadRequest(new { message = "Invalid role." });

        var user = await _db.Users.FindAsync(id);
        if (user is null) return NotFound(new { message = "User not found." });

        if (user.Role == dto.Role)
            return BadRequest(new { message = $"This user is already a {dto.Role}." });

        // Demoting the only administrator would lock everybody out of this panel.
        if (user.Role == "admin" && dto.Role != "admin" &&
            await _db.Users.CountAsync(u => u.Role == "admin" && u.IsActive) <= 1)
            return BadRequest(new { message = "Cannot demote the last remaining administrator." });

        var previous = user.Role;
        user.Role = dto.Role;
        user.SecurityStamp = DateTime.UtcNow;   // revokes existing tokens

        // A role that is no longer an organization should not keep a verified badge.
        if (dto.Role is not ("organization" or "employer") && user.VerificationStatus == "verified")
        {
            user.VerificationStatus = "unverified";
            user.VerifiedAt = null;
            user.VerifiedByUserId = null;
        }

        _notify.Raise(user.Id, "system", "Your account role changed",
            $"An administrator changed your role from {previous} to {dto.Role}. " +
            "Please sign in again to continue.");

        await _db.SaveChangesAsync();
        return Ok(new { message = "Role updated. The user must sign in again." });
    }

    /// <summary>
    /// DELETE /api/admin/users/5
    ///
    /// Accounts that carry financial history or reviews are DEACTIVATED, never
    /// erased: deleting them would destroy payment records that the other party
    /// still depends on. Only an account with no history is removed outright.
    /// Pass ?force=true to deactivate regardless.
    /// </summary>
    [HttpDelete("users/{id:int}")]
    public async Task<ActionResult> DeleteUser(int id, [FromQuery] string? reason)
    {
        var user = await _db.Users.FindAsync(id);
        if (user is null) return NotFound(new { message = "User not found." });

        if (user.Id == CurrentUserId)
            return BadRequest(new { message = "You cannot remove your own account." });

        if (user.Role == "admin" &&
            await _db.Users.CountAsync(u => u.Role == "admin" && u.IsActive) <= 1)
            return BadRequest(new { message = "Cannot delete the last remaining administrator." });

        var hasPayments = await _db.Payments.AnyAsync(p => p.WorkerId == id);
        var hasRatings  = await _db.Ratings.AnyAsync(r => r.AuthorId == id || r.SubjectId == id);
        var hasWork     = await _db.WorkRecords.AnyAsync(w => w.WorkerId == id);
        var hasJobs     = await _db.Jobs.AnyAsync(j => j.EmployerId == id);

        if (hasPayments || hasRatings || hasWork || hasJobs)
        {
            if (!user.IsActive)
                return BadRequest(new { message = "This account is already deactivated." });

            user.IsActive = false;
            user.DeactivatedAt = DateTime.UtcNow;
            user.DeactivationReason = (reason ?? "Deactivated by administrator").Trim();
            user.SecurityStamp = DateTime.UtcNow;   // signs them out everywhere

            // Their open postings stop accepting applications.
            var openJobs = await _db.Jobs
                .Where(j => j.EmployerId == id && j.Status == "open")
                .ToListAsync();
            foreach (var j in openJobs) j.Status = "closed";

            await _db.SaveChangesAsync();

            return Ok(new
            {
                message = "This account holds payment or review history, so it was deactivated " +
                          "instead of deleted. The financial records stay intact.",
                action = "deactivated"
            });
        }

        // No history at all — safe to remove completely.
        _db.Applications.RemoveRange(_db.Applications.Where(a => a.WorkerId == id));
        _db.Notifications.RemoveRange(_db.Notifications.Where(n => n.UserId == id));
        _db.Users.Remove(user);
        await _db.SaveChangesAsync();

        return Ok(new { message = "User deleted.", action = "deleted" });
    }

    /// <summary>PUT /api/admin/users/5/reactivate</summary>
    [HttpPut("users/{id:int}/reactivate")]
    public async Task<ActionResult> Reactivate(int id)
    {
        var user = await _db.Users.FindAsync(id);
        if (user is null) return NotFound(new { message = "User not found." });
        if (user.IsActive) return BadRequest(new { message = "This account is already active." });

        user.IsActive = true;
        user.DeactivatedAt = null;
        user.DeactivationReason = "";
        user.SecurityStamp = DateTime.UtcNow;

        _notify.Raise(user.Id, "system", "Your account has been reactivated",
            "You can sign in and use DailyWork again.");

        await _db.SaveChangesAsync();
        return Ok(new { message = "Account reactivated." });
    }

    // =================================================================
    // Jobs
    // =================================================================

    /// <summary>GET /api/admin/jobs — every job, whatever its status.</summary>
    [HttpGet("jobs")]
    public async Task<ActionResult> Jobs()
    {
        var jobs = await _db.Jobs
            .Include(j => j.Employer)
            .Include(j => j.Applications)
            .OrderByDescending(j => j.CreatedAt)
            .Select(j => new
            {
                j.Id, j.Title, j.Category, j.Location, j.Pay, j.Per,
                j.Status, j.Urgent, j.WorkersNeeded,
                EmployerName = j.Employer!.Name,
                EmployerVerified = j.Employer.VerificationStatus == "verified",
                Applications = j.Applications.Count,
                j.CreatedAt
            })
            .ToListAsync();

        return Ok(jobs);
    }

    /// <summary>
    /// DELETE /api/admin/jobs/5
    /// A job with completed work is closed rather than deleted, so the payment
    /// records attached to it survive.
    /// </summary>
    [HttpDelete("jobs/{id:int}")]
    public async Task<ActionResult> DeleteJob(int id)
    {
        var job = await _db.Jobs.FindAsync(id);
        if (job is null) return NotFound(new { message = "Job not found." });

        var hasPayments = await _db.Payments.AnyAsync(p => p.JobId == id);
        var hasCompleted = await _db.Applications
            .AnyAsync(a => a.JobId == id && a.Status == "completed");

        if (hasPayments || hasCompleted)
        {
            if (job.Status == "closed")
                return BadRequest(new { message = "This job is already closed." });

            job.Status = "closed";
            job.UpdatedAt = DateTime.UtcNow;
            await _db.SaveChangesAsync();

            return Ok(new
            {
                message = "This job has completed work and payment records attached, " +
                          "so it was closed instead of deleted.",
                action = "closed"
            });
        }

        _db.Applications.RemoveRange(_db.Applications.Where(a => a.JobId == id));
        _db.Jobs.Remove(job);
        await _db.SaveChangesAsync();

        return Ok(new { message = "Job deleted.", action = "deleted" });
    }

    // =================================================================
    // Organization verification
    // =================================================================

    /// <summary>GET /api/admin/verifications — the queue of pending requests.</summary>
    [HttpGet("verifications")]
    public async Task<ActionResult> Verifications([FromQuery] string? status)
    {
        var wanted = string.IsNullOrWhiteSpace(status) ? "pending" : status.Trim().ToLowerInvariant();

        var q = _db.Users.AsQueryable();
        if (wanted != "all") q = q.Where(u => u.VerificationStatus == wanted);
        else q = q.Where(u => u.VerificationStatus != "unverified");

        var rows = await q
            .OrderBy(u => u.VerificationRequestedAt)
            .Select(u => new VerificationRequestDto
            {
                UserId = u.Id,
                Name = u.Name,
                Email = u.Email,
                Phone = u.Phone,
                Role = u.Role,
                OrganizationName = u.OrganizationName,
                RegistrationNumber = u.RegistrationNumber,
                OrganizationAddress = u.OrganizationAddress,
                OrganizationWebsite = u.OrganizationWebsite,
                Notes = u.VerificationNotes,
                Status = u.VerificationStatus,
                RequestedAt = u.VerificationRequestedAt,
                DecisionNote = u.VerificationDecisionNote
            })
            .ToListAsync();

        return Ok(rows);
    }

    /// <summary>
    /// PUT /api/admin/verifications/5  body: { "approve": true, "note": "" }
    /// Approving is what turns on the Verified badge — nothing else does.
    /// </summary>
    [HttpPut("verifications/{userId:int}")]
    public async Task<ActionResult> Decide(int userId, [FromBody] VerificationDecisionDto dto)
    {
        var user = await _db.Users.FindAsync(userId);
        if (user is null) return NotFound(new { message = "User not found." });

        if (user.VerificationStatus != "pending")
            return BadRequest(new { message = "There is no pending verification request for this account." });

        if (dto.Approve)
        {
            user.VerificationStatus = "verified";
            user.VerifiedAt = DateTime.UtcNow;
            user.VerifiedByUserId = CurrentUserId;
            user.VerificationDecisionNote = (dto.Note ?? "").Trim();

            _notify.Raise(user.Id, "verification", "Your organization has been verified",
                "Your account now shows a verified badge on your job postings.");
        }
        else
        {
            var note = (dto.Note ?? "").Trim();
            if (note.Length < 5)
                return BadRequest(new { message = "Please give a reason when rejecting a request." });

            user.VerificationStatus = "rejected";
            user.VerificationDecisionNote = note;
            user.VerifiedAt = null;
            user.VerifiedByUserId = null;

            _notify.Raise(user.Id, "verification", "Verification request declined",
                $"Your verification request was not approved: {note} You may update your details and apply again.");
        }

        await _db.SaveChangesAsync();
        return Ok(new { message = dto.Approve ? "Organization verified." : "Request rejected." });
    }

    // =================================================================
    // Contact messages
    // =================================================================

    /// <summary>GET /api/admin/messages</summary>
    [HttpGet("messages")]
    public async Task<ActionResult> Messages()
    {
        var rows = await _db.ContactMessages
            .OrderByDescending(m => m.CreatedAt)
            .Take(200)
            .Select(m => new
            {
                m.Id, m.Name, m.Email, m.Subject, m.Message,
                m.Status, m.CreatedAt, m.HandledAt
            })
            .ToListAsync();

        return Ok(rows);
    }

    /// <summary>PUT /api/admin/messages/5  body: { "status": "answered" }</summary>
    [HttpPut("messages/{id:int}")]
    public async Task<ActionResult> UpdateMessage(int id, [FromBody] StatusDto dto)
    {
        var allowed = new[] { "new", "read", "answered" };
        var status = (dto.Status ?? "").Trim().ToLowerInvariant();
        if (!allowed.Contains(status))
            return BadRequest(new { message = "Invalid status." });

        var msg = await _db.ContactMessages.FindAsync(id);
        if (msg is null) return NotFound(new { message = "Message not found." });

        msg.Status = status;
        msg.HandledAt = status == "new" ? null : DateTime.UtcNow;

        await _db.SaveChangesAsync();
        return Ok(new { message = "Message updated." });
    }

    // =================================================================
    // Announcements
    // =================================================================

    /// <summary>
    /// POST /api/admin/announce  body: { "title": "...", "message": "...", "audience": "all" }
    /// Sends an administrative announcement to every user in the chosen group.
    /// </summary>
    [HttpPost("announce")]
    public async Task<ActionResult> Announce([FromBody] AnnouncementDto dto)
    {
        var title = (dto.Title ?? "").Trim();
        var body = (dto.Message ?? "").Trim();

        if (title.Length < 3 || body.Length < 5)
            return BadRequest(new { message = "Please enter a title and a message." });

        var audience = (dto.Audience ?? "all").Trim().ToLowerInvariant();
        var valid = new[] { "all", "worker", "employer", "organization" };
        if (!valid.Contains(audience))
            return BadRequest(new { message = "Invalid audience." });

        var recipients = await _db.Users
            .Where(u => u.IsActive && (audience == "all" || u.Role == audience))
            .Select(u => u.Id)
            .ToListAsync();

        foreach (var userId in recipients)
            _notify.Raise(userId, "announcement", title, body);

        await _db.SaveChangesAsync();
        return Ok(new { message = $"Announcement sent to {recipients.Count} user(s)." });
    }
}
