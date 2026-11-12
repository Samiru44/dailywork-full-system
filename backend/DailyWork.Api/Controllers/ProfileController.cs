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
[Route("api/profile")]
[Authorize]
public class ProfileController : ControllerBase
{
    private readonly AppDbContext _db;
    public ProfileController(AppDbContext db) => _db = db;

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/profile — the signed-in user's own profile and record.</summary>
    [HttpGet]
    public async Task<ActionResult<ProfileDto>> Get() => await BuildProfile(CurrentUserId, isOwner: true);

    /// <summary>
    /// GET /api/profile/5 — another user's public profile.
    /// Contact details are withheld unless the viewer is the owner, an
    /// administrator, or an employer who is actually dealing with this worker.
    /// </summary>
    [AllowAnonymous]
    [HttpGet("{id:int}")]
    public async Task<ActionResult<ProfileDto>> GetById(int id)
    {
        var viewerId = 0;
        if (this.User.Identity?.IsAuthenticated == true)
            int.TryParse(this.User.FindFirstValue(ClaimTypes.NameIdentifier), out viewerId);

        var isOwner = viewerId == id;
        var isAdmin = this.User.IsInRole("admin");

        // An employer may see contact details for someone who applied to them.
        var hasDealings = false;
        if (!isOwner && !isAdmin && viewerId > 0)
        {
            hasDealings = await _db.Applications
                .AnyAsync(a => a.WorkerId == id && a.Job!.EmployerId == viewerId);
        }

        return await BuildProfile(id, isOwner || isAdmin || hasDealings);
    }

    /// <summary>PUT /api/profile</summary>
    [HttpPut]
    public async Task<ActionResult> Update([FromBody] ProfileUpdateDto dto)
    {
        var user = await _db.Users.FindAsync(CurrentUserId);
        if (user is null) return NotFound(new { message = "User not found." });

        var name = (dto.Name ?? "").Trim();
        if (name.Length < 2)
            return BadRequest(new { message = "Please enter your full name." });

        var phone = (dto.Phone ?? "").Trim();
        var digits = phone.Count(char.IsDigit);
        if (digits < 9 || digits > 15)
            return BadRequest(new { message = "Please enter a valid phone number." });

        if (dto.ExperienceYears is < 0 or > 60)
            return BadRequest(new { message = "Years of experience must be between 0 and 60." });

        user.Name = name;
        user.Phone = phone;
        user.Skills = (dto.Skills ?? "").Trim();
        user.Location = (dto.Location ?? "").Trim();
        user.District = (dto.District ?? "").Trim();
        user.Bio = (dto.Bio ?? "").Trim();
        user.Experience = (dto.Experience ?? "").Trim();
        user.ExperienceYears = dto.ExperienceYears;
        user.Certifications = (dto.Certifications ?? "").Trim();
        user.Available = dto.Available;

        await _db.SaveChangesAsync();
        return Ok(new { message = "Profile updated." });
    }

    // =================================================================
    // CV
    // =================================================================

    /// <summary>
    /// POST /api/profile/cv — a worker uploads (or replaces) their CV.
    /// Sent as multipart/form-data with the file in a field named "file".
    ///
    /// The file type is checked twice: by its extension and by its first
    /// bytes. The stored content type is chosen here, not taken from the
    /// browser, and the size limit is enforced before anything is saved.
    /// </summary>
    [HttpPost("cv")]
    [Authorize(Roles = "worker")]
    [RequestSizeLimit(CvRules.MaxRequestBytes)]
    public async Task<ActionResult> UploadCv(IFormFile? file)
    {
        if (file is null || file.Length == 0)
            return BadRequest(new { message = "Please choose a file to upload." });

        if (file.Length > CvRules.MaxBytes)
            return BadRequest(new { message = "That file is too large. A CV can be up to 2 MB." });

        var fileName = CvRules.SafeFileName(file.FileName);
        var contentType = CvRules.ContentTypeFor(fileName);

        if (contentType is null)
            return BadRequest(new { message = "Please upload your CV as a " + CvRules.AllowedTypesText + "." });

        byte[] data;
        using (var buffer = new MemoryStream())
        {
            await file.CopyToAsync(buffer);
            data = buffer.ToArray();
        }

        if (!CvRules.MatchesItsType(fileName, data))
            return BadRequest(new
            {
                message = "That file does not look like a real " + CvRules.AllowedTypesText +
                          ". Please check the file and try again."
            });

        var me = CurrentUserId;

        // One CV per worker: uploading again replaces the earlier file.
        var cv = await _db.CvDocuments.FirstOrDefaultAsync(c => c.UserId == me);
        var replaced = cv is not null;

        if (cv is null)
        {
            cv = new CvDocument { UserId = me };
            _db.CvDocuments.Add(cv);
        }

        cv.FileName = fileName;
        cv.ContentType = contentType;
        cv.SizeBytes = data.LongLength;
        cv.Data = data;
        cv.UploadedAt = DateTime.UtcNow;

        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = replaced ? "Your CV has been replaced." : "Your CV has been uploaded.",
            fileName = cv.FileName,
            sizeBytes = cv.SizeBytes,
            uploadedAt = cv.UploadedAt
        });
    }

    /// <summary>GET /api/profile/cv — the signed-in user downloads their own CV.</summary>
    [HttpGet("cv")]
    public async Task<IActionResult> DownloadMyCv() => await SendCvAsync(CurrentUserId);

    /// <summary>
    /// GET /api/profile/5/cv — download a worker's CV.
    ///
    /// A CV holds personal details, so it is released only to the worker it
    /// belongs to, to an administrator, and to an employer that worker has
    /// applied to. Applying for a job is what shares the CV with that employer;
    /// nobody else can fetch it, even with the link.
    /// </summary>
    [HttpGet("{id:int}/cv")]
    public async Task<IActionResult> DownloadCv(int id)
    {
        var me = CurrentUserId;

        var allowed = me == id || this.User.IsInRole("admin");
        if (!allowed)
        {
            allowed = await _db.Applications
                .AnyAsync(a => a.WorkerId == id && a.Job!.EmployerId == me);
        }

        if (!allowed) return Forbid();

        return await SendCvAsync(id);
    }

    /// <summary>DELETE /api/profile/cv — the signed-in user removes their own CV.</summary>
    [HttpDelete("cv")]
    public async Task<ActionResult> DeleteCv()
    {
        var me = CurrentUserId;

        var cv = await _db.CvDocuments.FirstOrDefaultAsync(c => c.UserId == me);
        if (cv is null) return NotFound(new { message = "You have not uploaded a CV." });

        _db.CvDocuments.Remove(cv);
        await _db.SaveChangesAsync();

        return Ok(new { message = "Your CV has been removed." });
    }

    private async Task<IActionResult> SendCvAsync(int userId)
    {
        var cv = await _db.CvDocuments.AsNoTracking().FirstOrDefaultAsync(c => c.UserId == userId);
        if (cv is null) return NotFound(new { message = "No CV has been uploaded." });

        // Always offered as a download, never opened inside the site.
        Response.Headers["X-Content-Type-Options"] = "nosniff";
        return File(cv.Data, cv.ContentType, cv.FileName);
    }

    private async Task<ActionResult<ProfileDto>> BuildProfile(int id, bool isOwner)
    {
        var user = await _db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == id);
        if (user is null) return NotFound(new { message = "User not found." });

        var stars = await _db.Ratings.Where(r => r.SubjectId == id).Select(r => r.Stars).ToListAsync();
        var completed = await _db.Applications.CountAsync(a => a.WorkerId == id && a.Status == "completed");

        var earned = await _db.Payments
            .Where(p => p.WorkerId == id)
            .Select(p => p.AmountPaid)
            .ToListAsync();

        var history = await _db.Applications
            .Where(a => a.WorkerId == id && a.Status == "completed")
            .Include(a => a.Job).ThenInclude(j => j!.Employer)
            .OrderByDescending(a => a.CompletedAt)
            .Take(10)
            .Select(a => new WorkHistoryDto
            {
                JobId = a.JobId,
                JobTitle = a.Job!.Title,
                Category = a.Job.Category,
                Location = a.Job.Location,
                EmployerName = a.Job.Employer!.Name,
                CompletedAt = a.CompletedAt
            })
            .ToListAsync();

        // Only the CV's details are read here, never the file itself, and they
        // are passed on only to someone who is allowed to download it.
        var cv = await _db.CvDocuments
            .Where(c => c.UserId == id)
            .Select(c => new { c.FileName, c.SizeBytes, c.UploadedAt })
            .FirstOrDefaultAsync();

        var shownCv = isOwner ? cv : null;

        return Ok(new ProfileDto
        {
            Id = user.Id,
            Name = user.Name,

            // Personal contact details are only released to people entitled to them.
            Email = isOwner ? user.Email : "",
            Phone = isOwner ? user.Phone : "",

            Role = user.Role,
            Skills = user.Skills,
            Location = user.Location,
            District = user.District,
            Bio = user.Bio,
            Experience = user.Experience,
            ExperienceYears = user.ExperienceYears,
            Certifications = user.Certifications,
            Available = user.Available,
            VerificationStatus = user.VerificationStatus,
            IsVerified = user.VerificationStatus == "verified",
            CreatedAt = user.CreatedAt,

            AverageRating = stars.Count == 0 ? 0 : Math.Round(stars.Average(), 1),
            RatingCount = stars.Count,
            JobsCompleted = completed,

            // Earnings are private to the worker themselves.
            TotalEarned = isOwner ? earned.Sum() : 0m,

            HasCv = shownCv is not null,
            CvFileName = shownCv?.FileName ?? "",
            CvSizeBytes = shownCv?.SizeBytes ?? 0,
            CvUploadedAt = shownCv?.UploadedAt,

            WorkHistory = history
        });
    }
}
