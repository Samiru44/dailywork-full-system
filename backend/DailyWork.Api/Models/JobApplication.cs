namespace DailyWork.Api.Models;

public class JobApplication
{
    public int Id { get; set; }

    public int JobId { get; set; }
    public Job? Job { get; set; }

    public int WorkerId { get; set; }
    public User? Worker { get; set; }

    /// <summary>
    /// pending → shortlisted → accepted → completed, or pending/shortlisted → rejected.
    /// Transitions are enforced in ApplicationsController; see AllowedNext.
    /// </summary>
    public string Status { get; set; } = "pending";

    /// <summary>A short note the worker can add when applying.</summary>
    public string Message { get; set; } = "";

    // Timestamps give the lifecycle an audit trail.
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? ShortlistedAt { get; set; }
    public DateTime? AcceptedAt { get; set; }
    public DateTime? RejectedAt { get; set; }
    public DateTime? CompletedAt { get; set; }

    /// <summary>
    /// The only status changes the system permits. Anything else is rejected,
    /// which stops work being marked complete without first being hired and
    /// stops a finished job being pushed back to pending.
    /// </summary>
    public static readonly Dictionary<string, string[]> AllowedNext = new()
    {
        ["pending"]     = new[] { "shortlisted", "accepted", "rejected" },
        ["shortlisted"] = new[] { "accepted", "rejected" },
        ["accepted"]    = new[] { "completed", "rejected" },
        ["completed"]   = Array.Empty<string>(),   // terminal
        ["rejected"]    = Array.Empty<string>(),   // terminal
    };

    public static bool CanMove(string from, string to) =>
        AllowedNext.TryGetValue(from, out var next) && next.Contains(to);
}
