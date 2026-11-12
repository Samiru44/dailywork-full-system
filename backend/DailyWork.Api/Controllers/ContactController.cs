using System.Collections.Concurrent;
using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// The public Contact Us form. Messages are stored in the database and shown
/// to administrators, so the success message the sender sees is truthful.
/// </summary>
[ApiController]
[Route("api/contact")]
public class ContactController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly ILogger<ContactController> _log;

    public ContactController(AppDbContext db, ILogger<ContactController> log)
    {
        _db = db;
        _log = log;
    }

    // Simple per-address submission limit, enough to stop a form bot.
    private static readonly ConcurrentDictionary<string, List<DateTime>> Recent = new();
    private const int MaxPerHour = 5;

    /// <summary>POST /api/contact</summary>
    [HttpPost]
    public async Task<ActionResult> Send([FromBody] ContactMessageDto dto)
    {
        var name = (dto.Name ?? "").Trim();
        var email = (dto.Email ?? "").Trim().ToLowerInvariant();
        var subject = (dto.Subject ?? "").Trim();
        var body = (dto.Message ?? "").Trim();

        if (name.Length < 2)
            return BadRequest(new { message = "Please enter your name." });

        if (!email.Contains('@') || email.Length < 5)
            return BadRequest(new { message = "Please enter a valid email address." });

        if (subject.Length < 3)
            return BadRequest(new { message = "Please enter a subject." });

        if (body.Length < 10)
            return BadRequest(new { message = "Please write a little more detail in your message." });

        if (body.Length > 4000)
            return BadRequest(new { message = "Your message is too long. Please keep it under 4000 characters." });

        // Honeypot: a real person never fills a field the form hides.
        if (!string.IsNullOrWhiteSpace(dto.Website))
        {
            _log.LogInformation("Contact form honeypot triggered from {Ip}",
                HttpContext.Connection.RemoteIpAddress);

            // Answer as though it worked so a bot learns nothing.
            return Ok(new { message = "Thank you. Your message has been received." });
        }

        var key = HttpContext.Connection.RemoteIpAddress?.ToString() ?? email;
        var window = DateTime.UtcNow.AddHours(-1);
        var times = Recent.GetOrAdd(key, _ => new List<DateTime>());

        lock (times)
        {
            times.RemoveAll(t => t < window);
            if (times.Count >= MaxPerHour)
                return StatusCode(429, new
                {
                    message = "You have sent several messages recently. Please try again later."
                });
            times.Add(DateTime.UtcNow);
        }

        int? userId = null;
        if (this.User.Identity?.IsAuthenticated == true &&
            int.TryParse(this.User.FindFirstValue(ClaimTypes.NameIdentifier), out var uid))
            userId = uid;

        _db.ContactMessages.Add(new ContactMessage
        {
            Name = name,
            Email = email,
            Subject = subject,
            Message = body,
            Status = "new",
            UserId = userId
        });

        // Administrators see it in their notification list straight away.
        var admins = await _db.Users
            .Where(a => a.Role == "admin" && a.IsActive)
            .Select(a => a.Id)
            .ToListAsync();

        foreach (var adminId in admins)
        {
            _db.Notifications.Add(new Notification
            {
                UserId = adminId,
                Type = "message",
                Title = "New contact message",
                Message = $"{name} wrote about \"{subject}\"."
            });
        }

        await _db.SaveChangesAsync();

        return Ok(new { message = "Thank you. Your message has been received and our team will reply by email." });
    }
}
