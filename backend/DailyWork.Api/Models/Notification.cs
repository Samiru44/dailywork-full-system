namespace DailyWork.Api.Models;

/// <summary>
/// An in-app alert raised when something happens that a user should know about:
/// a new applicant, being hired, work verified, or a payment released.
/// </summary>
public class Notification
{
    public int Id { get; set; }

    public int UserId { get; set; }
    public User? User { get; set; }

    public string Title { get; set; } = "";
    public string Message { get; set; } = "";

    /// <summary>application | hired | rejected | completed | payment | rating | system</summary>
    public string Type { get; set; } = "system";

    public bool IsRead { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
