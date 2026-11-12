using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

[ApiController]
[Route("api/notifications")]
[Authorize]
public class NotificationsController : ControllerBase
{
    private readonly AppDbContext _db;
    public NotificationsController(AppDbContext db) => _db = db;

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/notifications</summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<NotificationDto>>> Mine()
    {
        var list = await _db.Notifications
            .Where(n => n.UserId == CurrentUserId)
            .OrderByDescending(n => n.CreatedAt)
            .Take(50)
            .Select(n => new NotificationDto
            {
                Id = n.Id,
                Title = n.Title,
                Message = n.Message,
                Type = n.Type,
                IsRead = n.IsRead,
                CreatedAt = n.CreatedAt
            })
            .ToListAsync();

        return Ok(list);
    }

    /// <summary>GET /api/notifications/unread-count — for the badge in the header.</summary>
    [HttpGet("unread-count")]
    public async Task<ActionResult> UnreadCount()
    {
        var count = await _db.Notifications
            .CountAsync(n => n.UserId == CurrentUserId && !n.IsRead);
        return Ok(new { count });
    }

    /// <summary>PUT /api/notifications/read-all</summary>
    [HttpPut("read-all")]
    public async Task<ActionResult> ReadAll()
    {
        var unread = await _db.Notifications
            .Where(n => n.UserId == CurrentUserId && !n.IsRead)
            .ToListAsync();

        foreach (var n in unread) n.IsRead = true;
        await _db.SaveChangesAsync();

        return Ok(new { message = "All notifications marked as read." });
    }

    /// <summary>PUT /api/notifications/5/read</summary>
    [HttpPut("{id:int}/read")]
    public async Task<ActionResult> Read(int id)
    {
        var n = await _db.Notifications.FirstOrDefaultAsync(x => x.Id == id && x.UserId == CurrentUserId);
        if (n is null) return NotFound(new { message = "Notification not found." });

        n.IsRead = true;
        await _db.SaveChangesAsync();
        return Ok(new { message = "Marked as read." });
    }
}
