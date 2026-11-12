namespace DailyWork.Api.Models;

/// <summary>
/// Job sectors, managed by administrators rather than hardcoded in the
/// frontend, so the category list can change without a code release.
/// </summary>
public class JobCategory
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";

    /// <summary>Font Awesome icon name used by the website, e.g. fa-helmet-safety.</summary>
    public string Icon { get; set; } = "fa-briefcase";

    public int SortOrder { get; set; }
    public bool IsActive { get; set; } = true;

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
