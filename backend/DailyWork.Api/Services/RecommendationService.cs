using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Services;

/// <summary>
/// Rule-based job matching.
///
/// The proposal asks for jobs to be recommended from a worker's skills,
/// location, experience and availability. This uses explainable scoring rather
/// than machine learning: every job gets points from a small number of clear
/// rules, and the reasons behind the score are returned with it, so a worker
/// can see exactly why a job was suggested and a marker can follow the logic.
///
/// Scores are normalised to 0–100 so they can be shown as a match percentage.
/// </summary>
public class RecommendationService
{
    private readonly AppDbContext _db;

    public RecommendationService(AppDbContext db) => _db = db;

    // Weights. Skills matter most, then being close enough to travel.
    private const int SkillWeight       = 40;   // spread across matched skills
    private const int CategoryWeight    = 15;
    private const int DistrictWeight    = 20;
    private const int LocationWeight    = 10;   // same town, on top of same district
    private const int ExperienceWeight  = 10;
    private const int WageWeight        = 10;
    private const int UrgencyWeight     = 5;
    private const int FreshnessWeight   = 5;

    /// <summary>
    /// Scores every open job for one worker and returns the best matches.
    /// Jobs the worker cannot actually take — their own postings, ones they
    /// already applied to, closed or fully-staffed ones — are excluded.
    /// </summary>
    public async Task<List<JobRecommendationDto>> ForWorkerAsync(int workerId, int take = 10)
    {
        var worker = await _db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == workerId);
        if (worker is null) return new List<JobRecommendationDto>();

        var appliedJobIds = await _db.Applications
            .Where(a => a.WorkerId == workerId)
            .Select(a => a.JobId)
            .ToListAsync();

        var candidates = await _db.Jobs
            .AsNoTracking()
            .Include(j => j.Employer)
            .Include(j => j.Applications)
            .Where(j => j.Status == "open"
                     && j.EmployerId != workerId
                     && !appliedJobIds.Contains(j.Id))
            .ToListAsync();

        var workerSkills = SplitSkills(worker.Skills);

        // What the worker has earned before, used to judge whether a wage is good.
        var pastRates = await _db.Payments
            .Where(p => p.WorkerId == workerId)
            .Select(p => p.AgreedRate)
            .ToListAsync();

        var typicalRate = pastRates.Count > 0 ? pastRates.Average() : 0m;

        var scored = new List<JobRecommendationDto>();

        foreach (var job in candidates)
        {
            // Skip postings that have already hired everyone they need.
            var hired = job.Applications.Count(a => a.Status is "accepted" or "completed");
            if (hired >= job.WorkersNeeded) continue;

            // Skip anything whose end date has passed.
            if (job.EndDate.HasValue && job.EndDate.Value.Date < DateTime.UtcNow.Date) continue;

            var reasons = new List<string>();
            var score = 0;

            // ---------- skills ----------
            var jobSkills = SplitSkills(job.RequiredSkills);
            if (jobSkills.Count > 0 && workerSkills.Count > 0)
            {
                var matched = jobSkills
                    .Where(req => workerSkills.Any(have => SkillsAlign(have, req)))
                    .ToList();

                if (matched.Count > 0)
                {
                    var share = (double)matched.Count / jobSkills.Count;
                    score += (int)Math.Round(SkillWeight * share);
                    reasons.Add(matched.Count == jobSkills.Count
                        ? $"You have all the skills asked for ({string.Join(", ", matched)})"
                        : $"Matches your skills: {string.Join(", ", matched)}");
                }
            }
            else if (workerSkills.Count > 0 && jobSkills.Count == 0)
            {
                // No specific requirement listed, so skills cannot rule it out.
                score += SkillWeight / 4;
            }

            // ---------- category ----------
            if (!string.IsNullOrWhiteSpace(job.Category) &&
                workerSkills.Any(s => SkillsAlign(s, job.Category)))
            {
                score += CategoryWeight;
                reasons.Add($"You work in {job.Category}");
            }

            // ---------- where the work is ----------
            var sameDistrict = !string.IsNullOrWhiteSpace(worker.District) &&
                               worker.District.Equals(job.District, StringComparison.OrdinalIgnoreCase);

            var sameTown = !string.IsNullOrWhiteSpace(worker.Location) &&
                           worker.Location.Equals(job.Location, StringComparison.OrdinalIgnoreCase);

            if (sameTown)
            {
                score += DistrictWeight + LocationWeight;
                reasons.Add($"In your area ({job.Location})");
            }
            else if (sameDistrict)
            {
                score += DistrictWeight;
                reasons.Add($"In your district ({job.District})");
            }

            // ---------- experience ----------
            if (worker.ExperienceYears >= 3 && jobSkills.Count > 0 &&
                jobSkills.Any(req => workerSkills.Any(have => SkillsAlign(have, req))))
            {
                score += ExperienceWeight;
                reasons.Add($"{worker.ExperienceYears} years of relevant experience");
            }

            // ---------- wage ----------
            if (typicalRate > 0 && job.Pay >= typicalRate)
            {
                score += WageWeight;
                reasons.Add(job.Pay > typicalRate
                    ? "Pays more than your usual rate"
                    : "Matches your usual rate");
            }
            else if (typicalRate == 0 && job.Pay > 0)
            {
                score += WageWeight / 2;
            }

            // ---------- urgency and freshness ----------
            if (job.Urgent)
            {
                score += UrgencyWeight;
                reasons.Add("Employer needs someone urgently");
            }

            var ageInDays = (DateTime.UtcNow - job.CreatedAt).TotalDays;
            if (ageInDays <= 3)
            {
                score += FreshnessWeight;
                if (ageInDays <= 1) reasons.Add("Posted today");
            }

            // A verified employer is worth calling out, though it adds no score
            // of its own — verification is about trust, not suitability.
            if (job.Employer is { VerificationStatus: "verified" })
                reasons.Add("Verified employer");

            // A job is only suggested when it scores AND the score can be explained.
            // Points that carry no reason (a fresh posting, a non-zero wage) are not
            // on their own a reason to recommend anything, and showing a card with no
            // explanation would be worse than showing nothing.
            if (score <= 0 || reasons.Count == 0) continue;

            var maxPossible = SkillWeight + CategoryWeight + DistrictWeight + LocationWeight +
                              ExperienceWeight + WageWeight + UrgencyWeight + FreshnessWeight;

            scored.Add(new JobRecommendationDto
            {
                Id = job.Id,
                Title = job.Title,
                Category = job.Category,
                Location = job.Location,
                District = job.District,
                Pay = job.Pay,
                Per = job.Per,
                Urgent = job.Urgent,
                RequiredSkills = job.RequiredSkills,
                EmployerName = job.Employer?.Name ?? "",
                EmployerVerified = job.Employer is { VerificationStatus: "verified" },
                CreatedAt = job.CreatedAt,
                MatchScore = Math.Min(100, (int)Math.Round(score * 100.0 / maxPossible)),
                Reasons = reasons
            });
        }

        return scored
            .OrderByDescending(r => r.MatchScore)
            .ThenByDescending(r => r.CreatedAt)
            .Take(take)
            .ToList();
    }

    /// <summary>
    /// Workers who suit a newly posted job, used to decide who should be told
    /// about it. Only workers marked available are considered.
    /// </summary>
    public async Task<List<(int WorkerId, int Score)>> WorkersForJobAsync(Job job, int minScore = 25, int take = 50)
    {
        var jobSkills = SplitSkills(job.RequiredSkills);

        var workers = await _db.Users
            .AsNoTracking()
            .Where(u => u.Role == "worker" && u.IsActive && u.Available)
            .Select(u => new { u.Id, u.Skills, u.District, u.Location, u.ExperienceYears })
            .ToListAsync();

        var results = new List<(int, int)>();

        foreach (var w in workers)
        {
            var have = SplitSkills(w.Skills);
            var score = 0;

            if (jobSkills.Count > 0 && have.Count > 0)
            {
                var matched = jobSkills.Count(req => have.Any(h => SkillsAlign(h, req)));
                if (matched > 0)
                    score += (int)Math.Round(SkillWeight * ((double)matched / jobSkills.Count));
            }

            if (have.Any(s => SkillsAlign(s, job.Category)))
                score += CategoryWeight;

            if (!string.IsNullOrWhiteSpace(w.Location) &&
                w.Location.Equals(job.Location, StringComparison.OrdinalIgnoreCase))
                score += DistrictWeight + LocationWeight;
            else if (!string.IsNullOrWhiteSpace(w.District) &&
                     w.District.Equals(job.District, StringComparison.OrdinalIgnoreCase))
                score += DistrictWeight;

            if (score >= minScore) results.Add((w.Id, score));
        }

        return results.OrderByDescending(r => r.Item2).Take(take).ToList();
    }

    // =================================================================
    // Text helpers
    // =================================================================

    private static List<string> SplitSkills(string? raw) =>
        string.IsNullOrWhiteSpace(raw)
            ? new List<string>()
            : raw.Split(new[] { ',', ';', '/', '|' }, StringSplitOptions.RemoveEmptyEntries)
                 .Select(s => s.Trim())
                 .Where(s => s.Length > 1)
                 .Distinct(StringComparer.OrdinalIgnoreCase)
                 .ToList();

    /// <summary>
    /// Loose skill comparison. Daily wage workers write their skills freely
    /// ("masonry", "mason work", "Mason"), so an exact string match would miss
    /// most real matches. Compares on a normalised stem and allows either side
    /// to contain the other.
    /// </summary>
    private static bool SkillsAlign(string a, string b)
    {
        var x = Normalise(a);
        var y = Normalise(b);

        if (x.Length == 0 || y.Length == 0) return false;
        if (x == y) return true;

        if (x.Length >= 4 && y.Length >= 4 && (x.Contains(y) || y.Contains(x)))
            return true;

        return Synonyms.TryGetValue(x, out var group) && group.Contains(y);
    }

    private static string Normalise(string s)
    {
        var cleaned = new string(s.Trim().ToLowerInvariant()
            .Where(c => char.IsLetterOrDigit(c) || c == ' ')
            .ToArray()).Trim();

        // Strip common endings so "painting" and "painter" line up.
        foreach (var suffix in new[] { "ing", "er", "ers", "s" })
        {
            if (cleaned.Length > 4 && cleaned.EndsWith(suffix))
                return cleaned[..^suffix.Length];
        }

        return cleaned;
    }

    /// <summary>Terms that mean the same job in this sector.</summary>
    private static readonly Dictionary<string, string[]> Synonyms = new(StringComparer.OrdinalIgnoreCase)
    {
        ["mason"]        = new[] { "masonry", "brick", "block", "construction", "build" },
        ["construction"] = new[] { "mason", "masonry", "build", "site", "labour", "labor" },
        ["paint"]        = new[] { "painting", "painter", "decorat" },
        ["clean"]        = new[] { "cleaning", "cleaner", "housekeep", "janitor" },
        ["driv"]         = new[] { "driving", "driver", "transport", "deliver", "lorry" },
        ["deliver"]      = new[] { "delivery", "driv", "transport", "courier" },
        ["farm"]         = new[] { "farming", "agriculture", "harvest", "plant", "cultivat" },
        ["agricultur"]   = new[] { "farm", "harvest", "plant", "estate" },
        ["secur"]        = new[] { "security", "guard", "watchman" },
        ["carpent"]      = new[] { "carpentry", "wood", "furnitur" },
        ["electric"]     = new[] { "electrical", "electrician", "wiring" },
        ["plumb"]        = new[] { "plumbing", "plumber", "pipe" },
        ["weld"]         = new[] { "welding", "welder", "fabricat" },
        ["load"]         = new[] { "loading", "unload", "warehous", "packing" },
        ["warehous"]     = new[] { "load", "storage", "packing", "manufactur" },
        ["cook"]         = new[] { "cooking", "kitchen", "chef", "catering" },
        ["garden"]       = new[] { "gardening", "landscap", "lawn" },
    };
}
