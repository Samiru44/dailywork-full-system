using System.ComponentModel.DataAnnotations;

namespace DailyWork.Api.Dtos;

// =====================================================================
// Auth
// =====================================================================

public class RegisterDto
{
    [Required] public string Name { get; set; } = "";
    [Required, EmailAddress] public string Email { get; set; } = "";
    [Required] public string Phone { get; set; } = "";
    [Required, MinLength(8)] public string Password { get; set; } = "";
    [Required] public string Role { get; set; } = "worker";
}

public class LoginDto
{
    [Required, EmailAddress] public string Email { get; set; } = "";
    [Required] public string Password { get; set; } = "";
}

/// <summary>Shape the frontend expects back from register/login.</summary>
public class AuthResponseDto
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public string Role { get; set; } = "";
    public string VerificationStatus { get; set; } = "unverified";
    public string Token { get; set; } = "";
}

// =====================================================================
// Jobs
// =====================================================================

/// <summary>Everything the Find Jobs page can filter and sort by.</summary>
public class JobSearchQuery
{
    public string? Search { get; set; }
    public string? Category { get; set; }
    public string? Location { get; set; }
    public string? District { get; set; }
    public decimal? MinPay { get; set; }
    public decimal? MaxPay { get; set; }
    public string? Skills { get; set; }
    public bool? UrgentOnly { get; set; }
    public bool? AvailableOnly { get; set; }
    public bool? VerifiedOnly { get; set; }

    /// <summary>relevance | newest | wage_high | wage_low</summary>
    public string? Sort { get; set; }

    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 20;
}

public class JobDto
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Category { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public string Description { get; set; } = "";
    public string RequiredSkills { get; set; } = "";
    public decimal Pay { get; set; }
    public string Per { get; set; } = "day";
    public bool Urgent { get; set; }
    public string Status { get; set; } = "open";
    public int WorkersNeeded { get; set; }
    public int ExpectedUnits { get; set; }
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }
    public int EmployerId { get; set; }
    public string EmployerName { get; set; } = "";
    public bool EmployerVerified { get; set; }
    public int Applications { get; set; }
    public int PositionsFilled { get; set; }
    public DateTime CreatedAt { get; set; }
}

public class JobCreateDto
{
    [Required] public string Title { get; set; } = "";
    [Required] public string Category { get; set; } = "";
    [Required] public string Location { get; set; } = "";
    public string? District { get; set; }
    public string? Description { get; set; }
    public string? RequiredSkills { get; set; }
    [Range(0, 1000000)] public decimal Pay { get; set; }
    public string Per { get; set; } = "day";
    public bool Urgent { get; set; }
    public int WorkersNeeded { get; set; } = 1;
    public int ExpectedUnits { get; set; } = 1;
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }

    /// <summary>Optional organization project this posting belongs to.</summary>
    public int? ProjectId { get; set; }
}

/// <summary>A recommended job, with the reasons it was suggested.</summary>
public class JobRecommendationDto
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Category { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public decimal Pay { get; set; }
    public string Per { get; set; } = "day";
    public bool Urgent { get; set; }
    public string RequiredSkills { get; set; } = "";
    public string EmployerName { get; set; } = "";
    public bool EmployerVerified { get; set; }
    public DateTime CreatedAt { get; set; }

    /// <summary>0–100 match strength.</summary>
    public int MatchScore { get; set; }

    /// <summary>Plain-language explanation of the score.</summary>
    public List<string> Reasons { get; set; } = new();
}

// =====================================================================
// Applications
// =====================================================================

public class ApplyDto
{
    public int JobId { get; set; }
    public string? Message { get; set; }
}

public class ApplicationDto
{
    public int Id { get; set; }
    public int JobId { get; set; }
    public string JobTitle { get; set; } = "";
    public string EmployerName { get; set; } = "";
    public string Location { get; set; } = "";
    public decimal Pay { get; set; }
    public string Per { get; set; } = "day";
    public string Status { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime? AcceptedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
}

public class StatusDto
{
    [Required] public string Status { get; set; } = "";
}

// =====================================================================
// Work records
// =====================================================================

public class WorkRecordCreateDto
{
    public DateTime? WorkDate { get; set; }
    public decimal Units { get; set; } = 1m;
    public string? Notes { get; set; }
}

public class WorkRecordDto
{
    public int Id { get; set; }
    public DateTime WorkDate { get; set; }
    public decimal Units { get; set; }
    public string Unit { get; set; } = "day";
    public decimal RateApplied { get; set; }
    public decimal LineTotal { get; set; }
    public string Notes { get; set; } = "";
    public bool Verified { get; set; }

    /// <summary>approved | pending | rejected</summary>
    public string Status { get; set; } = "approved";
    public string DecisionNote { get; set; } = "";
    public bool SubmittedByWorker { get; set; }
}

/// <summary>The employer's decision on a day the worker submitted.</summary>
public class WorkDecisionDto
{
    public bool Approve { get; set; }
    public string? Note { get; set; }
}

// =====================================================================
// Payments
// =====================================================================

public class PaymentDto
{
    public int Id { get; set; }
    public int JobId { get; set; }
    public string JobTitle { get; set; } = "";
    public string EmployerName { get; set; } = "";
    public decimal AgreedRate { get; set; }
    public string RateUnit { get; set; } = "day";
    public decimal UnitsWorked { get; set; }
    public decimal Amount { get; set; }
    public decimal AmountPaid { get; set; }
    public decimal Outstanding { get; set; }
    public string Status { get; set; } = "";
    public string Method { get; set; } = "";
    public string Notes { get; set; } = "";
    public bool WorkerConfirmed { get; set; }

    /// <summary>How much of the amount paid the worker has confirmed receiving.</summary>
    public decimal ConfirmedAmount { get; set; }

    /// <summary>Money recorded as paid that the worker has not yet confirmed.</summary>
    public decimal AwaitingConfirmation { get; set; }

    public DateTime? WorkerConfirmedAt { get; set; }
    public DateTime? PaidAt { get; set; }
    public DateTime CreatedAt { get; set; }
}

public class PaymentRecordDto
{
    /// <summary>Leave empty to settle the whole outstanding balance.</summary>
    public decimal? Amount { get; set; }

    /// <summary>cash | bank transfer | mobile — how the employer says they paid.</summary>
    public string? Method { get; set; }

    public string? Notes { get; set; }
}

public class DisputeDto
{
    [Required] public string Note { get; set; } = "";
}

// =====================================================================
// Ratings
// =====================================================================

public class RatingCreateDto
{
    public int JobId { get; set; }
    public int SubjectId { get; set; }
    [Range(1, 5)] public int Stars { get; set; }
    public string? Comment { get; set; }
}

public class RatingDto
{
    public int Id { get; set; }
    public int JobId { get; set; }
    public string JobTitle { get; set; } = "";
    public string AuthorName { get; set; } = "";
    public string SubjectName { get; set; } = "";
    public int Stars { get; set; }
    public string Comment { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

// =====================================================================
// Notifications
// =====================================================================

public class NotificationDto
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Message { get; set; } = "";
    public string Type { get; set; } = "";
    public bool IsRead { get; set; }
    public DateTime CreatedAt { get; set; }
}

// =====================================================================
// Profile
// =====================================================================

public class ProfileDto
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public string Role { get; set; } = "";
    public string Skills { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public string Bio { get; set; } = "";
    public string Experience { get; set; } = "";
    public int ExperienceYears { get; set; }
    public string Certifications { get; set; } = "";
    public bool Available { get; set; }
    public string VerificationStatus { get; set; } = "unverified";
    public bool IsVerified { get; set; }
    public DateTime CreatedAt { get; set; }

    public double AverageRating { get; set; }
    public int RatingCount { get; set; }
    public int JobsCompleted { get; set; }
    public decimal TotalEarned { get; set; }

    // The uploaded CV. Only the file's details are sent here, never its
    // contents, and only to the people allowed to download it: the worker
    // themselves, an administrator, or an employer the worker has applied to.
    public bool HasCv { get; set; }
    public string CvFileName { get; set; } = "";
    public long CvSizeBytes { get; set; }
    public DateTime? CvUploadedAt { get; set; }

    /// <summary>Recent completed work, shown as a work history.</summary>
    public List<WorkHistoryDto> WorkHistory { get; set; } = new();
}

public class WorkHistoryDto
{
    public int JobId { get; set; }
    public string JobTitle { get; set; } = "";
    public string Category { get; set; } = "";
    public string Location { get; set; } = "";
    public string EmployerName { get; set; } = "";
    public DateTime? CompletedAt { get; set; }
}

public class ProfileUpdateDto
{
    [Required] public string Name { get; set; } = "";
    [Required] public string Phone { get; set; } = "";
    public string? Skills { get; set; }
    public string? Location { get; set; }
    public string? District { get; set; }
    public string? Bio { get; set; }
    public string? Experience { get; set; }
    public int ExperienceYears { get; set; }
    public string? Certifications { get; set; }
    public bool Available { get; set; } = true;
}

// =====================================================================
// Employer workspace
// =====================================================================

public class ApplicantDto
{
    public int Id { get; set; }
    public int JobId { get; set; }
    public string JobTitle { get; set; } = "";
    public int WorkerId { get; set; }
    public string WorkerName { get; set; } = "";
    public string WorkerPhone { get; set; } = "";
    public string WorkerEmail { get; set; } = "";
    public string WorkerSkills { get; set; } = "";
    public string WorkerExperience { get; set; } = "";
    public int WorkerExperienceYears { get; set; }
    public string WorkerLocation { get; set; } = "";
    public double WorkerRating { get; set; }
    public int WorkerJobsCompleted { get; set; }

    /// <summary>True when the worker has a CV on file that this employer may download.</summary>
    public bool WorkerHasCv { get; set; }
    public string WorkerCvFileName { get; set; } = "";

    public string Message { get; set; } = "";
    public string Status { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public class EmployerPaymentDto
{
    public int Id { get; set; }
    public string JobTitle { get; set; } = "";
    public string WorkerName { get; set; } = "";
    public int WorkerId { get; set; }
    public int JobId { get; set; }
    public decimal AgreedRate { get; set; }
    public string RateUnit { get; set; } = "day";
    public decimal UnitsWorked { get; set; }
    public decimal Amount { get; set; }
    public decimal AmountPaid { get; set; }
    public decimal Outstanding { get; set; }
    public string Status { get; set; } = "";
    public bool WorkerConfirmed { get; set; }

    /// <summary>How much of the amount paid the worker has confirmed receiving.</summary>
    public decimal ConfirmedAmount { get; set; }

    /// <summary>
    /// Money the employer has recorded that the worker has not yet confirmed.
    /// Shown to the employer so they can see a part payment is still unconfirmed
    /// rather than assuming the whole record is agreed.
    /// </summary>
    public decimal AwaitingConfirmation { get; set; }

    public DateTime? PaidAt { get; set; }
    public DateTime CreatedAt { get; set; }
}

// =====================================================================
// Organization verification
// =====================================================================

public class OrganizationDto
{
    public int UserId { get; set; }
    public string OrganizationName { get; set; } = "";
    public string RegistrationNumber { get; set; } = "";
    public string Address { get; set; } = "";
    public string Website { get; set; } = "";
    public string District { get; set; } = "";
    public string Notes { get; set; } = "";
    public string VerificationStatus { get; set; } = "unverified";
    public DateTime? RequestedAt { get; set; }
    public DateTime? VerifiedAt { get; set; }
    public string DecisionNote { get; set; } = "";
}

public class OrganizationUpdateDto
{
    [Required] public string OrganizationName { get; set; } = "";
    public string? RegistrationNumber { get; set; }
    public string? Address { get; set; }
    public string? Website { get; set; }
    public string? District { get; set; }
}

public class VerificationRequestCreateDto
{
    public string? Notes { get; set; }
}

public class VerificationRequestDto
{
    public int UserId { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public string Role { get; set; } = "";
    public string OrganizationName { get; set; } = "";
    public string RegistrationNumber { get; set; } = "";
    public string OrganizationAddress { get; set; } = "";
    public string OrganizationWebsite { get; set; } = "";
    public string Notes { get; set; } = "";
    public string Status { get; set; } = "";
    public DateTime? RequestedAt { get; set; }
    public string DecisionNote { get; set; } = "";
}

public class VerificationDecisionDto
{
    public bool Approve { get; set; }
    public string? Note { get; set; }
}

// =====================================================================
// Administration
// =====================================================================

public class RoleDto
{
    [Required] public string Role { get; set; } = "";
}

public class AnnouncementDto
{
    [Required] public string Title { get; set; } = "";
    [Required] public string Message { get; set; } = "";

    /// <summary>all | worker | employer | organization</summary>
    public string? Audience { get; set; } = "all";
}

public class JobCategoryDto
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public string Icon { get; set; } = "";
    public int SortOrder { get; set; }
    public bool IsActive { get; set; }
    public int OpenJobs { get; set; }
}

public class JobCategoryWriteDto
{
    [Required] public string Name { get; set; } = "";
    public string? Description { get; set; }
    public string? Icon { get; set; }
    public int SortOrder { get; set; }
    public bool? IsActive { get; set; }
}

// =====================================================================
// Contact
// =====================================================================

public class ContactMessageDto
{
    [Required] public string Name { get; set; } = "";
    [Required, EmailAddress] public string Email { get; set; } = "";
    [Required] public string Subject { get; set; } = "";
    [Required] public string Message { get; set; } = "";

    /// <summary>
    /// Honeypot. The form hides this field, so only an automated submission
    /// ever fills it in.
    /// </summary>
    public string? Website { get; set; }
}

// =====================================================================
// Organization projects and recruitment tracking
// =====================================================================

public class ProjectCreateDto
{
    public string? Name { get; set; }
    public string? Description { get; set; }
    public string? Location { get; set; }
    public string? District { get; set; }
    public int WorkersRequired { get; set; }
    public decimal Budget { get; set; }
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }
    public string? Status { get; set; }
}

/// <summary>One job posted under a project, with its own hiring position.</summary>
public class ProjectJobDto
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Status { get; set; } = "";
    public string Location { get; set; } = "";
    public decimal Pay { get; set; }
    public string Per { get; set; } = "day";
    public int WorkersNeeded { get; set; }
    public int Applicants { get; set; }
    public int Hired { get; set; }
}

/// <summary>
/// A project with its recruitment and cost position. Every figure here is
/// derived from the jobs, applications and payments that belong to it.
/// </summary>
public class ProjectDto
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public string Location { get; set; } = "";
    public string District { get; set; } = "";
    public string Status { get; set; } = "";
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }
    public decimal Budget { get; set; }
    public DateTime CreatedAt { get; set; }

    // Recruitment
    public int WorkersRequired { get; set; }
    public int PositionsPosted { get; set; }
    public int JobsPosted { get; set; }
    public int OpenJobs { get; set; }
    public int Applicants { get; set; }
    public int Shortlisted { get; set; }
    public int Hired { get; set; }
    public int Completed { get; set; }
    public int StillNeeded { get; set; }
    public double FillRate { get; set; }

    // Cost
    public decimal Committed { get; set; }
    public decimal Paid { get; set; }
    public decimal Outstanding { get; set; }
    public double BudgetUsed { get; set; }
    public bool OverBudget { get; set; }

    public List<ProjectJobDto> Jobs { get; set; } = new();
}


// =====================================================================
// Report email request
// =====================================================================

public class ReportEmailDto
{
    [Required]
    public string Report { get; set; } = "";
}
