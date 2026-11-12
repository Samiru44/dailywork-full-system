using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

[ApiController]
[Route("api/auth")]
public class AuthController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly TokenService _tokens;
    private readonly LoginThrottle _throttle;
    private readonly ILogger<AuthController> _log;

    public AuthController(AppDbContext db, TokenService tokens, LoginThrottle throttle,
                          ILogger<AuthController> log)
    {
        _db = db;
        _tokens = tokens;
        _throttle = throttle;
        _log = log;
    }

    private string? ClientIp => HttpContext.Connection.RemoteIpAddress?.ToString();

    /// <summary>POST /api/auth/register</summary>
    [HttpPost("register")]
    public async Task<ActionResult<AuthResponseDto>> Register([FromBody] RegisterDto dto)
    {
        // The public form must never be able to create an administrator.
        var allowed = new[] { "worker", "employer", "organization" };
        if (!allowed.Contains(dto.Role))
            return BadRequest(new { message = "Admin accounts cannot be self-registered." });

        var name = (dto.Name ?? "").Trim();
        if (name.Length < 2)
            return BadRequest(new { message = "Please enter your full name." });

        var email = (dto.Email ?? "").Trim().ToLowerInvariant();
        if (!email.Contains('@') || email.Length < 5)
            return BadRequest(new { message = "Please enter a valid email address." });

        var phone = (dto.Phone ?? "").Trim();
        var digits = phone.Count(char.IsDigit);
        if (digits < 9 || digits > 15)
            return BadRequest(new { message = "Please enter a valid phone number." });

        var passwordProblem = PasswordPolicy.Validate(dto.Password, email, name);
        if (passwordProblem is not null)
            return BadRequest(new { message = passwordProblem });

        if (await _db.Users.AnyAsync(u => u.Email == email))
            return Conflict(new { message = "An account with this email already exists." });

        var user = new User
        {
            Name = name,
            Email = email,
            Phone = phone,
            Role = dto.Role,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(dto.Password),

            // Organizations start unverified and must request verification.
            VerificationStatus = "unverified",
            OrganizationName = dto.Role == "organization" ? name : ""
        };

        _db.Users.Add(user);
        await _db.SaveChangesAsync();

        _db.Notifications.Add(new Notification
        {
            UserId = user.Id,
            Type = "system",
            Title = "Welcome to DailyWork",
            Message = dto.Role == "worker"
                ? "Add your skills and location to your profile so we can recommend jobs that suit you."
                : dto.Role == "organization"
                    ? "Complete your organization details and request verification to earn a verified badge."
                    : "Post your first job to start receiving applications."
        });
        await _db.SaveChangesAsync();

        return Ok(BuildResponse(user));
    }

    /// <summary>POST /api/auth/login</summary>
    [HttpPost("login")]
    public async Task<ActionResult<AuthResponseDto>> Login([FromBody] LoginDto dto)
    {
        var email = (dto.Email ?? "").Trim().ToLowerInvariant();

        // Rate limiting comes before any database work so that a lockout cannot
        // be used to measure whether an account exists.
        if (_throttle.RetryAfter(email, ClientIp) is { } wait)
        {
            Response.Headers.RetryAfter = ((int)wait.TotalSeconds).ToString();
            return StatusCode(429, new
            {
                message = $"Too many failed login attempts. Please try again in {Math.Ceiling(wait.TotalMinutes)} minute(s)."
            });
        }

        var user = await _db.Users.FirstOrDefaultAsync(u => u.Email == email);

        if (user is null || !BCrypt.Net.BCrypt.Verify(dto.Password ?? "", user.PasswordHash))
        {
            _throttle.RecordFailure(email, ClientIp);
            _log.LogWarning("Failed login for {Email} from {Ip}", email, ClientIp);

            // The same message either way, so the response cannot be used to
            // discover which email addresses are registered.
            return Unauthorized(new { message = "Invalid email or password." });
        }

        if (!user.IsActive)
        {
            _log.LogWarning("Login attempt on deactivated account {UserId}", user.Id);
            return Unauthorized(new
            {
                message = "This account has been deactivated. Please contact support."
            });
        }

        _throttle.RecordSuccess(email, ClientIp);
        return Ok(BuildResponse(user));
    }

    private AuthResponseDto BuildResponse(User user) => new()
    {
        Id = user.Id,
        Name = user.Name,
        Email = user.Email,
        Role = user.Role,
        VerificationStatus = user.VerificationStatus,
        Token = _tokens.CreateToken(user)
    };
}
