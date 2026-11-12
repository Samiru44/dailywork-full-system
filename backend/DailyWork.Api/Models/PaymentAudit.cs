namespace DailyWork.Api.Models;

/// <summary>
/// An append-only record of every change made to a payment. Nothing in the
/// application updates or deletes these rows, so the financial history of a
/// job can always be reconstructed.
/// </summary>
public class PaymentAudit
{
    public int Id { get; set; }

    public int PaymentId { get; set; }
    public Payment? Payment { get; set; }

    /// <summary>created | recorded | confirmed | disputed | adjusted</summary>
    public string Action { get; set; } = "";

    public string FromStatus { get; set; } = "";
    public string ToStatus { get; set; } = "";
    public decimal AmountAtChange { get; set; }

    /// <summary>Who made the change.</summary>
    public int ActorUserId { get; set; }
    public string ActorRole { get; set; } = "";

    public string Note { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
