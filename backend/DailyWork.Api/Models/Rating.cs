namespace DailyWork.Api.Models;

/// <summary>
/// A review left after a job is completed. Both sides can rate each other,
/// which is what builds reputation and trust on the platform.
/// </summary>
public class Rating
{
    public int Id { get; set; }

    public int JobId { get; set; }
    public Job? Job { get; set; }

    /// <summary>The user writing the review.</summary>
    public int AuthorId { get; set; }
    public User? Author { get; set; }

    /// <summary>The user being reviewed.</summary>
    public int SubjectId { get; set; }
    public User? Subject { get; set; }

    /// <summary>1 to 5 stars.</summary>
    public int Stars { get; set; }

    public string Comment { get; set; } = "";

    /// <summary>worker | employer — which side the subject was on for this job.</summary>
    public string SubjectRole { get; set; } = "worker";

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
