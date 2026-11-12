namespace DailyWork.Api.Models;

/// <summary>A message submitted through the public Contact Us form.</summary>
public class ContactMessage
{
    public int Id { get; set; }

    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public string Subject { get; set; } = "";
    public string Message { get; set; } = "";

    /// <summary>new | read | answered</summary>
    public string Status { get; set; } = "new";

    /// <summary>Set when the sender was signed in at the time.</summary>
    public int? UserId { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? HandledAt { get; set; }
}
