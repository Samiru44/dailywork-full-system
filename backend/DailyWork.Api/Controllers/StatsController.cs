using DailyWork.Api.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

[ApiController]
[Route("api/stats")]
public class StatsController : ControllerBase
{
    private readonly AppDbContext _db;
    public StatsController(AppDbContext db) => _db = db;

    /// <summary>
    /// GET /api/stats — public counters for the home page.
    ///
    /// These are the real numbers held in the database. An earlier version
    /// raised them to a minimum display value, which overstated how many people
    /// actually used the platform; that has been removed. The response also
    /// states plainly whether the figures still include the demonstration data
    /// that ships with a fresh installation, so the website can label them.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult> Get()
    {
        var workers      = await _db.Users.CountAsync(u => u.Role == "worker" && u.IsActive);
        var employers    = await _db.Users.CountAsync(u =>
                               (u.Role == "employer" || u.Role == "organization") && u.IsActive);
        var verified     = await _db.Users.CountAsync(u => u.VerificationStatus == "verified");
        var jobsPosted   = await _db.Jobs.CountAsync();
        var openJobs     = await _db.Jobs.CountAsync(j => j.Status == "open");
        var applications = await _db.Applications.CountAsync();
        var completed    = await _db.Applications.CountAsync(a => a.Status == "completed");

        var paidAmounts = await _db.Payments
            .Where(p => p.AmountPaid > 0)
            .Select(p => p.AmountPaid)
            .ToListAsync();

        // The seeded demonstration accounts all use the dailywork.lk address.
        // Both counts are reported, because a figure of "4 workers" is only
        // honest if the visitor can see how many of those are sample rows.
        // The flag stays true while ANY demonstration record remains — one real
        // registration does not turn seeded data into genuine usage.
        var demoUsers = await _db.Users.CountAsync(u => u.Email.EndsWith("@dailywork.lk"));
        var realUsers = await _db.Users.CountAsync(u => !u.Email.EndsWith("@dailywork.lk"));

        return Ok(new
        {
            workers,
            employers,
            verifiedEmployers = verified,
            jobsPosted,
            openJobs,
            applications,
            jobsCompleted = completed,
            totalPaid = paidAmounts.Sum(),

            // Lets the website say honestly what the visitor is looking at.
            isDemoData = demoUsers > 0,
            demoUserCount = demoUsers,
            realUserCount = realUsers
        });
    }
}
