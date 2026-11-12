namespace DailyWork.Api.Models;

public class User
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public string PasswordHash { get; set; } = "";

    /// <summary>worker | employer | organization | admin</summary>
    public string Role { get; set; } = "worker";

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // ---------------------------------------------------------------
    // Account state
    // ---------------------------------------------------------------

    /// <summary>
    /// Soft-delete flag. Accounts that hold financial history are deactivated
    /// rather than deleted, so payment records and reviews stay intact.
    /// </summary>
    public bool IsActive { get; set; } = true;

    public DateTime? DeactivatedAt { get; set; }
    public string DeactivationReason { get; set; } = "";

    /// <summary>
    /// Bumped whenever the account's privileges change (role change,
    /// deactivation). Tokens issued before this stamp are refused, so an old
    /// JWT cannot keep using a privilege that has since been revoked.
    /// </summary>
    public DateTime SecurityStamp { get; set; } = DateTime.UtcNow;

    // ---------------------------------------------------------------
    // Profile (editable by the user)
    // ---------------------------------------------------------------

    public string Skills { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public string Bio { get; set; } = "";
    public bool Available { get; set; } = true;

    /// <summary>Free-text work experience, e.g. "8 years masonry, 2 years painting".</summary>
    public string Experience { get; set; } = "";

    /// <summary>Years of experience, used by the recommendation scoring.</summary>
    public int ExperienceYears { get; set; }

    /// <summary>Certifications or training, comma separated.</summary>
    public string Certifications { get; set; } = "";

    // ---------------------------------------------------------------
    // Organization verification (role = organization, and employers who apply)
    // ---------------------------------------------------------------

    /// <summary>unverified | pending | verified | rejected</summary>
    public string VerificationStatus { get; set; } = "unverified";

    public string OrganizationName { get; set; } = "";
    public string RegistrationNumber { get; set; } = "";
    public string OrganizationAddress { get; set; } = "";
    public string OrganizationWebsite { get; set; } = "";

    /// <summary>What the applicant submitted in support of the request.</summary>
    public string VerificationNotes { get; set; } = "";

    /// <summary>Administrator's reason when a request is rejected.</summary>
    public string VerificationDecisionNote { get; set; } = "";

    public DateTime? VerificationRequestedAt { get; set; }
    public DateTime? VerifiedAt { get; set; }
    public int? VerifiedByUserId { get; set; }

    /// <summary>True only after an administrator has actually approved the account.</summary>
    public bool IsVerified => VerificationStatus == "verified";

    // ---------------------------------------------------------------
    // Navigation
    // ---------------------------------------------------------------

    public List<Job> JobsPosted { get; set; } = new();
    public List<JobApplication> Applications { get; set; } = new();
    public List<Payment> Payments { get; set; } = new();
    public List<Notification> Notifications { get; set; } = new();
}
