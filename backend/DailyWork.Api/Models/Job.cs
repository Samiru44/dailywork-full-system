namespace DailyWork.Api.Models;

public class Job
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Category { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public string Description { get; set; } = "";

    /// <summary>The agreed wage rate for one unit of work (see <see cref="Per"/>).</summary>
    public decimal Pay { get; set; }

    /// <summary>day | shift | hour — the unit the wage rate is quoted in.</summary>
    public string Per { get; set; } = "day";

    public bool Urgent { get; set; }

    /// <summary>open | filled | closed</summary>
    public string Status { get; set; } = "open";

    /// <summary>Skills the employer is asking for, comma separated.</summary>
    public string RequiredSkills { get; set; } = "";

    /// <summary>How many workers this posting needs.</summary>
    public int WorkersNeeded { get; set; } = 1;

    /// <summary>Expected number of days or shifts of work.</summary>
    public int ExpectedUnits { get; set; } = 1;

    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; set; }

    public int EmployerId { get; set; }
    public User? Employer { get; set; }

    /// <summary>
    /// The organization project this posting belongs to, if any. Optional, so
    /// an individual employer's jobs and an organization's one-off jobs are
    /// unaffected.
    /// </summary>
    public int? ProjectId { get; set; }
    public Project? Project { get; set; }

    public List<JobApplication> Applications { get; set; } = new();
}
