using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Payment tracking.
///
/// IMPORTANT: this system records what the two parties say happened. It does
/// not move money and it does not verify an electronic transfer. An employer
/// records that they paid; the worker then confirms they received it. The value
/// of the record is that both sides see the same history and neither can change
/// it silently — every change is written to an append-only audit trail.
/// </summary>
[ApiController]
[Route("api/payments")]
[Authorize]
public class PaymentsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly NotificationService _notify;

    public PaymentsController(AppDbContext db, NotificationService notify)
    {
        _db = db;
        _notify = notify;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);
    private string CurrentRole => this.User.FindFirstValue(ClaimTypes.Role) ?? "";

    // =================================================================
    // Worker view
    // =================================================================

    /// <summary>GET /api/payments/mine — the signed-in worker's payment history.</summary>
    [HttpGet("mine")]
    public async Task<ActionResult<IEnumerable<PaymentDto>>> Mine()
    {
        var me = CurrentUserId;

        var payments = await _db.Payments
            .Where(p => p.WorkerId == me)
            .Include(p => p.Job).ThenInclude(j => j!.Employer)
            .OrderByDescending(p => p.CreatedAt)
            .Select(p => new PaymentDto
            {
                Id = p.Id,
                JobId = p.JobId,
                JobTitle = p.Job!.Title,
                EmployerName = p.Job.Employer!.Name,
                AgreedRate = p.AgreedRate,
                RateUnit = p.RateUnit,
                UnitsWorked = p.UnitsWorked,
                Amount = p.Amount,
                AmountPaid = p.AmountPaid,
                Status = p.Status,
                Method = p.Method,
                Notes = p.Notes,
                WorkerConfirmed = p.WorkerConfirmed,
                ConfirmedAmount = p.ConfirmedAmount,
                AwaitingConfirmation = p.AmountPaid - p.ConfirmedAmount,
                WorkerConfirmedAt = p.WorkerConfirmedAt,
                PaidAt = p.PaidAt,
                CreatedAt = p.CreatedAt
            })
            .ToListAsync();

        // Outstanding is derived, so it is filled in after the query.
        foreach (var p in payments) p.Outstanding = p.Amount - p.AmountPaid;

        return Ok(payments);
    }

    /// <summary>GET /api/payments/5/audit — the full change history of one payment.</summary>
    [HttpGet("{id:int}/audit")]
    public async Task<ActionResult> Audit(int id)
    {
        var payment = await _db.Payments
            .Include(p => p.Job)
            .FirstOrDefaultAsync(p => p.Id == id);

        if (payment is null) return NotFound(new { message = "Payment not found." });

        var me = CurrentUserId;
        if (payment.WorkerId != me && payment.Job!.EmployerId != me && !this.User.IsInRole("admin"))
            return Forbid();

        var trail = await _db.PaymentAudits
            .Where(a => a.PaymentId == id)
            .OrderBy(a => a.CreatedAt)
            .Select(a => new
            {
                a.Id, a.Action, a.FromStatus, a.ToStatus,
                a.AmountAtChange, a.ActorRole, a.Note, a.CreatedAt
            })
            .ToListAsync();

        return Ok(trail);
    }

    // =================================================================
    // Employer records a payment
    // =================================================================

    /// <summary>
    /// PUT /api/payments/5/pay
    /// body: { "amount": 2400, "method": "cash", "notes": "" }
    ///
    /// Records that the employer has handed over money. Amount is optional —
    /// leaving it out settles the whole outstanding balance. Part payments are
    /// supported, which is what daily wage work usually looks like in practice.
    /// </summary>
    [HttpPut("{id:int}/pay")]
    [Authorize(Roles = "employer,organization,admin")]
    public async Task<ActionResult> RecordPayment(int id, [FromBody] PaymentRecordDto? dto)
    {
        var payment = await _db.Payments
            .Include(p => p.Job)
            .Include(p => p.Worker)
            .FirstOrDefaultAsync(p => p.Id == id);

        if (payment is null) return NotFound(new { message = "Payment not found." });
        if (payment.Job!.EmployerId != CurrentUserId && !this.User.IsInRole("admin")) return Forbid();

        // A settled payment is never reopened — this is what protects the
        // original PaidAt timestamp from being overwritten by a second call.
        if (payment.Status == "paid")
            return BadRequest(new
            {
                message = "This payment has already been settled in full and cannot be changed."
            });

        var outstanding = payment.Amount - payment.AmountPaid;
        if (outstanding <= 0)
            return BadRequest(new { message = "There is nothing outstanding on this payment." });

        // No amount given means settle everything that is left.
        var amount = dto?.Amount is > 0
            ? decimal.Round(dto.Amount!.Value, 2, MidpointRounding.AwayFromZero)
            : outstanding;

        if (amount <= 0)
            return BadRequest(new { message = "The payment amount must be greater than zero." });

        if (amount > outstanding)
            return BadRequest(new
            {
                message = $"That is more than the outstanding balance of {outstanding:0.00}."
            });

        await using var tx = await _db.Database.BeginTransactionAsync();
        try
        {
            var from = payment.Status;

            payment.AmountPaid = decimal.Round(payment.AmountPaid + amount, 2, MidpointRounding.AwayFromZero);
            payment.Method = (dto?.Method ?? payment.Method ?? "").Trim();
            if (!string.IsNullOrWhiteSpace(dto?.Notes)) payment.Notes = dto!.Notes!.Trim();

            var nowSettled = payment.AmountPaid >= payment.Amount;
            payment.Status = nowSettled ? "paid" : "partial";

            // The timestamp is written once, when the balance is first cleared.
            if (nowSettled && payment.PaidAt is null)
                payment.PaidAt = DateTime.UtcNow;

            // There is now money the worker has not acknowledged, so their
            // earlier confirmation no longer covers the whole amount paid.
            // Without this, a payment settled in two instalments would show as
            // fully confirmed when only the first instalment ever was.
            var hadConfirmed = payment.WorkerConfirmed;
            if (payment.AmountPaid > payment.ConfirmedAmount)
                payment.WorkerConfirmed = false;

            _db.PaymentAudits.Add(new PaymentAudit
            {
                PaymentId = payment.Id,
                Action = "recorded",
                FromStatus = from,
                ToStatus = payment.Status,
                AmountAtChange = amount,
                ActorUserId = CurrentUserId,
                ActorRole = CurrentRole,
                Note = (nowSettled
                    ? $"Employer recorded final payment of {amount:0.00}."
                    : $"Employer recorded part payment of {amount:0.00}; " +
                      $"{payment.Amount - payment.AmountPaid:0.00} still outstanding.")
                    + (hadConfirmed && !payment.WorkerConfirmed
                        ? $" Worker confirmation reset: {payment.AwaitingConfirmation:0.00} " +
                          "of the amount paid is not yet confirmed."
                        : "")
            });

            _notify.Raise(payment.WorkerId, "payment",
                nowSettled ? "Payment recorded in full" : "Part payment recorded",
                nowSettled
                    ? $"Rs. {amount:N2} for \"{payment.Job.Title}\" was recorded as paid. " +
                      "Please confirm once you have received it."
                    : $"Rs. {amount:N2} for \"{payment.Job.Title}\" was recorded. " +
                      $"Rs. {payment.Amount - payment.AmountPaid:N2} is still outstanding. " +
                      "Please confirm what you have received so far.");

            await _db.SaveChangesAsync();
            await tx.CommitAsync();

            return Ok(new
            {
                message = nowSettled ? "Payment recorded in full." : "Part payment recorded.",
                status = payment.Status,
                amountPaid = payment.AmountPaid,
                outstanding = payment.Amount - payment.AmountPaid,
                workerConfirmed = payment.WorkerConfirmed,
                awaitingConfirmation = payment.AwaitingConfirmation
            });
        }
        catch
        {
            await tx.RollbackAsync();
            throw;
        }
    }

    // =================================================================
    // Worker confirms or disputes
    // =================================================================

    /// <summary>
    /// PUT /api/payments/5/confirm — the worker states that the money actually
    /// arrived. This is what turns an employer's claim into an agreed record.
    /// </summary>
    [HttpPut("{id:int}/confirm")]
    [Authorize(Roles = "worker")]
    public async Task<ActionResult> Confirm(int id)
    {
        var payment = await _db.Payments
            .Include(p => p.Job)
            .FirstOrDefaultAsync(p => p.Id == id);

        if (payment is null) return NotFound(new { message = "Payment not found." });
        if (payment.WorkerId != CurrentUserId) return Forbid();

        if (payment.AmountPaid <= 0)
            return BadRequest(new { message = "The employer has not recorded any payment yet." });

        // Confirmation covers an amount, not the record as a whole. If the
        // worker has already confirmed everything paid so far there is nothing
        // new to confirm; once the employer pays more, this becomes available
        // again automatically.
        var newlyReceived = payment.AwaitingConfirmation;
        if (newlyReceived <= 0)
            return BadRequest(new
            {
                message = "You have already confirmed everything recorded as paid so far." +
                          (payment.Outstanding > 0
                              ? $" Rs. {payment.Outstanding:N2} of this job is still unpaid."
                              : "")
            });

        var confirmedBefore = payment.ConfirmedAmount;

        payment.ConfirmedAmount = payment.AmountPaid;
        payment.WorkerConfirmed = true;
        payment.WorkerConfirmedAt = DateTime.UtcNow;

        var fullySettled = payment.Status == "paid";

        _db.PaymentAudits.Add(new PaymentAudit
        {
            PaymentId = payment.Id,
            Action = "confirmed",
            FromStatus = payment.Status,
            ToStatus = payment.Status,
            AmountAtChange = newlyReceived,
            ActorUserId = CurrentUserId,
            ActorRole = CurrentRole,
            Note = confirmedBefore > 0
                ? $"Worker confirmed a further {newlyReceived:0.00} " +
                  $"(total confirmed {payment.ConfirmedAmount:0.00} of {payment.Amount:0.00})."
                : $"Worker confirmed receipt of {newlyReceived:0.00} of {payment.Amount:0.00}."
        });

        _notify.Raise(payment.Job!.EmployerId, "payment", "Payment confirmed by worker",
            fullySettled
                ? $"The worker confirmed receiving the full amount for \"{payment.Job.Title}\"."
                : $"The worker confirmed receiving Rs. {payment.ConfirmedAmount:N2} for " +
                  $"\"{payment.Job.Title}\". Rs. {payment.Outstanding:N2} is still outstanding.");

        await _db.SaveChangesAsync();

        return Ok(new
        {
            message = fullySettled
                ? "Thank you, the full payment has been confirmed."
                : $"Thank you. You have confirmed Rs. {payment.ConfirmedAmount:N2} of " +
                  $"Rs. {payment.Amount:N2}. You will be asked to confirm again when the " +
                  "employer pays the balance.",
            confirmedAmount = payment.ConfirmedAmount,
            outstanding = payment.Outstanding,
            fullyConfirmed = fullySettled
        });
    }

    /// <summary>
    /// PUT /api/payments/5/dispute  body: { "note": "..." }
    /// Lets a worker flag that the recorded payment does not match reality.
    /// The record is never deleted; the dispute is added to the audit trail.
    /// </summary>
    [HttpPut("{id:int}/dispute")]
    [Authorize(Roles = "worker")]
    public async Task<ActionResult> Dispute(int id, [FromBody] DisputeDto dto)
    {
        var payment = await _db.Payments
            .Include(p => p.Job)
            .FirstOrDefaultAsync(p => p.Id == id);

        if (payment is null) return NotFound(new { message = "Payment not found." });
        if (payment.WorkerId != CurrentUserId) return Forbid();

        var note = (dto.Note ?? "").Trim();
        if (note.Length < 5)
            return BadRequest(new { message = "Please explain the problem in a few words." });

        payment.WorkerConfirmed = false;
        payment.WorkerDisputeNote = note;

        _db.PaymentAudits.Add(new PaymentAudit
        {
            PaymentId = payment.Id,
            Action = "disputed",
            FromStatus = payment.Status,
            ToStatus = payment.Status,
            AmountAtChange = payment.AmountPaid,
            ActorUserId = CurrentUserId,
            ActorRole = CurrentRole,
            Note = note
        });

        _notify.Raise(payment.Job!.EmployerId, "payment", "Payment disputed",
            $"The worker raised a problem with the payment for \"{payment.Job.Title}\": {note}");

        await _db.SaveChangesAsync();
        return Ok(new { message = "Your dispute has been recorded and the employer notified." });
    }
}
