namespace DailyWork.Api.Models;

/// <summary>
/// A piece of work an organization is recruiting for, that several job
/// postings belong to — a site, a contract, a season's harvest.
///
/// This is what separates an organization from an individual employer. An
/// employer posts a job at a time; an organization runs projects, each needing
/// a number of people across several postings, and needs to see recruitment
/// progress and cost per project rather than per job.
///
/// Jobs reference a project optionally, so an organization can still post a
/// one-off job without creating a project for it, and nothing changes for
/// ordinary employers.
/// </summary>
public class Project
{
    public int Id { get; set; }

    /// <summary>The organization that owns this project.</summary>
    public int OrganizationId { get; set; }
    public User? Organization { get; set; }

    public string Name { get; set; } = "";
    public string Description { get; set; } = "";

    public string Location { get; set; } = "";
    public string District { get; set; } = "";

    /// <summary>
    /// How many people the project needs in total. Recruitment progress is
    /// measured against this, across every job posted under the project.
    /// </summary>
    public int WorkersRequired { get; set; }

    /// <summary>Budget set aside, used to compare planned against actual spend.</summary>
    public decimal Budget { get; set; }

    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }

    /// <summary>planning | active | completed | cancelled</summary>
    public string Status { get; set; } = "planning";

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; set; }

    public List<Job> Jobs { get; set; } = new();
}
