using DailyWork.Api.Data;
using DailyWork.Api.Models;

namespace DailyWork.Api.Services;

/// <summary>
/// Raises in-app alerts. Kept in one place so every part of the system
/// words its notifications the same way.
/// </summary>
public class NotificationService
{
    private readonly AppDbContext _db;
    public NotificationService(AppDbContext db) => _db = db;

    /// <summary>Queues a notification. The caller still has to SaveChanges.</summary>
    public void Raise(int userId, string type, string title, string message)
    {
        _db.Notifications.Add(new Notification
        {
            UserId = userId,
            Type = type,
            Title = title,
            Message = message
        });
    }
}
