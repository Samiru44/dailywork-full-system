using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Organization details and the verification request workflow.
///
/// An account is never verified automatically. It submits its details, an
/// administrator reviews them, and only an approval sets the verified badge.
/// </summary>
[ApiController]
[Route("api/organization")]
[Authorize(Roles = "organization,employer,admin")]
public class OrganizationController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;

    public OrganizationController(AppDbContext db, NotificationService notify)
    {
        _db = db;
        _notify = notify;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/organization — the caller's own organization record.</summary>
    [HttpGet]
    public async Task<ActionResult<OrganizationDto>> Get()
    {
        var u = await _db.Users.FindAsync(CurrentUserId);
        if (u is null) return NotFound(new { message = "Account not found." });

        return Ok(new OrganizationDto
        {
            UserId = u.Id,
            OrganizationName = u.OrganizationName,
            RegistrationNumber = u.RegistrationNumber,
            Address = u.OrganizationAddress,
            Website = u.OrganizationWebsite,
            District = u.District,
            Notes = u.VerificationNotes,
            VerificationStatus = u.VerificationStatus,
            RequestedAt = u.VerificationRequestedAt,
            VerifiedAt = u.VerifiedAt,
            DecisionNote = u.VerificationDecisionNote
        });
    }

    /// <summary>
    /// PUT /api/organization — saves the organization's details.
    /// Editing details after being verified sends the account back for review,
    /// so a verified badge always reflects what an administrator actually saw.
    /// </summary>
    [HttpPut]
    public async Task<ActionResult> Update([FromBody] OrganizationUpdateDto dto)
    {
        var u = await _db.Users.FindAsync(CurrentUserId);
        if (u is null) return NotFound(new { message = "Account not found." });

        var name = (dto.OrganizationName ?? "").Trim();
        if (name.Length < 2)
            return BadRequest(new { message = "Please enter the organization name." });

        var wasVerified = u.VerificationStatus == "verified";
        var detailsChanged =
            !string.Equals(u.OrganizationName, name, StringComparison.Ordinal) ||
            !string.Equals(u.RegistrationNumber, (dto.RegistrationNumber ?? "").Trim(), StringComparison.Ordinal);

        u.OrganizationName = name;
        u.RegistrationNumber = (dto.RegistrationNumber ?? "").Trim();
        u.OrganizationAddress = (dto.Address ?? "").Trim();
        u.OrganizationWebsite = (dto.Website ?? "").Trim();
        if (!string.IsNullOrWhiteSpace(dto.District)) u.District = dto.District.Trim();

        if (wasVerified && detailsChanged)
        {
            u.VerificationStatus = "pending";
            u.VerificationRequestedAt = DateTime.UtcNow;
            u.VerifiedAt = null;
            u.VerifiedByUserId = null;
            u.VerificationDecisionNote = "Details changed after verification; awaiting review.";
        }

        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = wasVerified && detailsChanged
                ? "Details saved. Because the registered details changed, your account is awaiting review again."
                : "Organization details saved.",
            verificationStatus = u.VerificationStatus
        });
    }

    /// <summary>
    /// POST /api/organization/verify — asks an administrator to verify the account.
    /// </summary>
    [HttpPost("verify")]
    public async Task<ActionResult> RequestVerification([FromBody] VerificationRequestCreateDto? dto)
    {
        var u = await _db.Users.FindAsync(CurrentUserId);
        if (u is null) return NotFound(new { message = "Account not found." });

        if (u.VerificationStatus == "verified")
            return BadRequest(new { message = "This account is already verified." });

        if (u.VerificationStatus == "pending")
            return BadRequest(new { message = "Your request is already waiting for review." });

        if (string.IsNullOrWhiteSpace(u.OrganizationName))
            return BadRequest(new { message = "Please save your organization name before requesting verification." });

        if (string.IsNullOrWhiteSpace(u.RegistrationNumber))
            return BadRequest(new { message = "A business or organization registration number is required." });

        u.VerificationStatus = "pending";
        u.VerificationRequestedAt = DateTime.UtcNow;
        u.VerificationNotes = (dto?.Notes ?? "").Trim();
        u.VerificationDecisionNote = "";

        // Tell the administrators there is something to review.
        var admins = await _db.Users
            .Where(a => a.Role == "admin" && a.IsActive)
            .Select(a => a.Id)
            .ToListAsync();

        foreach (var adminId in admins)
            _notify.Raise(adminId, "verification", "Verification request",
                $"{u.OrganizationName} ({u.Email}) requested organization verification.");

        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = "Your verification request has been submitted for review.",
            verificationStatus = u.VerificationStatus
        });
    }
}
