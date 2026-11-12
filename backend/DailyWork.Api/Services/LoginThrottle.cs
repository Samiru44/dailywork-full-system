using System.Collections.Concurrent;

namespace DailyWork.Api.Services;

/// <summary>
/// Simple in-memory login rate limiter. Counts failures per email and per
/// client address and locks the pair out for a short period once the limit is
/// reached, which stops a script from guessing passwords quickly.
///
/// In-memory state is adequate for a single-instance deployment like this one;
/// a multi-server deployment would move the same counters into a shared cache.
/// </summary>
public class LoginThrottle
{
    private const int MaxAttempts = 5;
    private static readonly TimeSpan Window = TimeSpan.FromMinutes(15);
    private static readonly TimeSpan Lockout = TimeSpan.FromMinutes(15);

    private sealed class Entry
    {
        public int Failures;
        public DateTime FirstFailureUtc;
        public DateTime? LockedUntilUtc;
    }

    private readonly ConcurrentDictionary<string, Entry> _entries = new();

    private static string Key(string email, string? ip) =>
        $"{email.Trim().ToLowerInvariant()}|{ip ?? "unknown"}";

    /// <summary>How long the caller must wait, or null when they may try now.</summary>
    public TimeSpan? RetryAfter(string email, string? ip)
    {
        if (!_entries.TryGetValue(Key(email, ip), out var e)) return null;

        if (e.LockedUntilUtc is { } until)
        {
            if (until > DateTime.UtcNow) return until - DateTime.UtcNow;

            // Lockout expired — clear it so the user starts fresh.
            e.LockedUntilUtc = null;
            e.Failures = 0;
        }

        return null;
    }

    public void RecordFailure(string email, string? ip)
    {
        var entry = _entries.GetOrAdd(Key(email, ip), _ => new Entry
        {
            FirstFailureUtc = DateTime.UtcNow
        });

        lock (entry)
        {
            // Start a new window if the previous one has gone stale.
            if (DateTime.UtcNow - entry.FirstFailureUtc > Window)
            {
                entry.Failures = 0;
                entry.FirstFailureUtc = DateTime.UtcNow;
            }

            entry.Failures++;

            if (entry.Failures >= MaxAttempts)
                entry.LockedUntilUtc = DateTime.UtcNow.Add(Lockout);
        }
    }

    public void RecordSuccess(string email, string? ip) =>
        _entries.TryRemove(Key(email, ip), out _);
}
