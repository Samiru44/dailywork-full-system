using System.Security.Claims;
using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Recommended jobs for the signed-in worker. See RecommendationService for
/// the scoring rules — each suggestion carries the reasons behind it.
/// </summary>
[ApiController]
[Route("api/recommendations")]
// Job recommendations are matched against a worker's skills, district and
// history, so they only mean anything for a worker. A bare [Authorize] let an
// employer or an administrator call this and receive a meaningless list.
[Authorize(Roles = "worker")]
public class RecommendationsController : ControllerBase
{
    private readonly RecommendationService _recommender;
    private readonly AppDbContext _db;

    public RecommendationsController(RecommendationService recommender, AppDbContext db)
    {
        _recommender = recommender;
        _db = db;
    }

    private int CurrentUserId => int.Parse(this.User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>GET /api/recommendations?take=10</summary>
    [HttpGet]
    public async Task<ActionResult> Mine([FromQuery] int take = 10)
    {
        if (take is < 1 or > 50) take = 10;

        var me = await _db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == CurrentUserId);
        if (me is null) return NotFound(new { message = "User not found." });

        if (me.Role != "worker")
            return Ok(new
            {
                recommendations = Array.Empty<JobRecommendationDto>(),
                message = "Job recommendations are for worker accounts."
            });

        var list = await _recommender.ForWorkerAsync(CurrentUserId, take);

        // A worker with an empty profile cannot be matched on anything, so say
        // so plainly rather than returning a silently empty list.
        var profileIsBare = string.IsNullOrWhiteSpace(me.Skills) &&
                            string.IsNullOrWhiteSpace(me.District) &&
                            string.IsNullOrWhiteSpace(me.Location);

        return Ok(new
        {
            recommendations = list,
            profileComplete = !profileIsBare,
            message = profileIsBare
                ? "Add your skills and district to your profile to get job recommendations that suit you."
                : list.Count == 0
                    ? "No matching jobs right now. New postings are matched against your profile as they arrive."
                    : null
        });
    }
}
