namespace DailyWork.Api.Models;

/// <summary>
/// One day, shift or block of hours a worker actually worked on a job.
/// This is what makes multi-day daily-wage work trackable: the employer
/// records each unit, and the payment total is derived from the sum.
/// </summary>
public class WorkRecord
{
    public int Id { get; set; }

    public int JobId { get; set; }
    public Job? Job { get; set; }

    public int WorkerId { get; set; }
    public User? Worker { get; set; }

    public int ApplicationId { get; set; }
    public JobApplication? Application { get; set; }

    /// <summary>The date the work was done.</summary>
    public DateTime WorkDate { get; set; }

    /// <summary>Number of units worked on that date (days, shifts or hours).</summary>
    public decimal Units { get; set; } = 1m;

    /// <summary>day | shift | hour</summary>
    public string Unit { get; set; } = "day";

    /// <summary>The rate agreed for this record, captured at the time.</summary>
    public decimal RateApplied { get; set; }

    /// <summary>RateApplied × Units.</summary>
    public decimal LineTotal { get; set; }

    public string Notes { get; set; } = "";

    /// <summary>Set once the employer confirms this particular day was worked.</summary>
    public bool Verified { get; set; }
    public DateTime? VerifiedAt { get; set; }

    /// <summary>
    /// approved | pending | rejected
    ///
    /// A day the employer enters themselves is "approved" immediately. A day
    /// the worker submits is "pending" until the employer approves it. Only
    /// approved records count towards what the worker is owed, so a worker
    /// cannot inflate their own payment by submitting extra days.
    /// </summary>
    public string Status { get; set; } = "approved";

    /// <summary>Who entered this record — the employer or the worker.</summary>
    public int SubmittedByUserId { get; set; }

    /// <summary>Set when the employer rejects a submitted day, so the worker learns why.</summary>
    public string DecisionNote { get; set; } = "";

    /// <summary>True when the worker entered this record rather than the employer.</summary>
    public bool SubmittedByWorker => SubmittedByUserId == WorkerId;

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
