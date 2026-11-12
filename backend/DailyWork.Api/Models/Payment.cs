namespace DailyWork.Api.Models;

public class Payment
{
    public int Id { get; set; }

    public int JobId { get; set; }
    public Job? Job { get; set; }

    public int WorkerId { get; set; }
    public User? Worker { get; set; }

    /// <summary>The application this payment settles. One payment per application.</summary>
    public int? ApplicationId { get; set; }
    public JobApplication? Application { get; set; }

    // ---------------- wage calculation ----------------

    /// <summary>The agreed rate per unit, copied from the job when work is verified.</summary>
    public decimal AgreedRate { get; set; }

    /// <summary>day | shift | hour</summary>
    public string RateUnit { get; set; } = "day";

    /// <summary>How many days, shifts or hours were actually worked.</summary>
    public decimal UnitsWorked { get; set; } = 1m;

    /// <summary>AgreedRate × UnitsWorked — the total owed for this job.</summary>
    public decimal Amount { get; set; }

    /// <summary>How much of <see cref="Amount"/> has actually been handed over.</summary>
    public decimal AmountPaid { get; set; }

    /// <summary>What is still owed. Kept as a computed property so it cannot drift.</summary>
    public decimal Outstanding => Amount - AmountPaid;

    // ---------------- status ----------------

    /// <summary>pending | partial | paid</summary>
    public string Status { get; set; } = "pending";

    public DateTime? PaidAt { get; set; }

    /// <summary>
    /// The employer's own record of how the money changed hands (cash, bank
    /// transfer, mobile wallet). This is a record of a claim, not a verified
    /// electronic transfer — the system does not move money.
    /// </summary>
    public string Method { get; set; } = "";

    public string Notes { get; set; } = "";

    // ---------------- worker confirmation ----------------

    /// <summary>
    /// Set when the worker confirms they actually received the money. Until
    /// then the payment is only the employer's claim.
    /// </summary>
    /// <summary>
    /// True when the worker has confirmed receiving everything paid so far.
    ///
    /// This is deliberately not a one-way flag. A worker may confirm a part
    /// payment, and the employer may then pay the balance; at that point there
    /// is new money the worker has not acknowledged, so recording a further
    /// payment sets this back to false and the worker is asked to confirm
    /// again. Without that reset a payment settled in two instalments would
    /// show as fully confirmed when only the first instalment ever was.
    /// </summary>
    public bool WorkerConfirmed { get; set; }

    /// <summary>
    /// How much the worker has actually confirmed receiving. Lets a part
    /// payment be acknowledged honestly: "confirmed Rs. 3,000 of Rs. 7,200".
    /// </summary>
    public decimal ConfirmedAmount { get; set; }

    public DateTime? WorkerConfirmedAt { get; set; }
    public string WorkerDisputeNote { get; set; } = "";

    /// <summary>Money recorded as paid that the worker has not yet confirmed.</summary>
    public decimal AwaitingConfirmation => AmountPaid - ConfirmedAmount;

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public List<PaymentAudit> AuditTrail { get; set; } = new();
}
