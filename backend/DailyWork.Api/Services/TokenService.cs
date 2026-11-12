using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using DailyWork.Api.Models;
using Microsoft.IdentityModel.Tokens;

namespace DailyWork.Api.Services;

/// <summary>Issues the signed JWT the browser stores and sends back on every request.</summary>
public class TokenService
{
    public const string SecurityStampClaim = "dw_stamp";

    private readonly IConfiguration _config;

    public TokenService(IConfiguration config) => _config = config;

    public string CreateToken(User user)
    {
        var claims = new List<Claim>
        {
            new(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new(ClaimTypes.Name, user.Name),
            new(ClaimTypes.Email, user.Email),
            new(ClaimTypes.Role, user.Role),

            // Lets the server reject a token that was issued before the
            // account's privileges last changed.
            new(SecurityStampClaim, user.SecurityStamp.Ticks.ToString())
        };

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(JwtKey(_config)));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var hours = double.TryParse(_config["Jwt:ExpiryHours"], out var h) ? h : 24;

        var token = new JwtSecurityToken(
            issuer: _config["Jwt:Issuer"],
            audience: _config["Jwt:Audience"],
            claims: claims,
            expires: DateTime.UtcNow.AddHours(hours),
            signingCredentials: creds);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    /// <summary>
    /// Resolves the signing key. The key is taken from the environment first
    /// (DAILYWORK_JWT_KEY or Jwt__Key) so that a real deployment never keeps its
    /// secret in source control. When nothing is configured — the normal case on
    /// a student machine — a key is generated once and written to a local file
    /// that is excluded from git, so each installation still gets its own secret.
    /// </summary>
    public static string JwtKey(IConfiguration config)
    {
        var fromEnv = Environment.GetEnvironmentVariable("DAILYWORK_JWT_KEY");
        if (!string.IsNullOrWhiteSpace(fromEnv) && fromEnv.Length >= 32) return fromEnv;

        var fromConfig = config["Jwt:Key"];
        if (!string.IsNullOrWhiteSpace(fromConfig) && fromConfig.Length >= 32) return fromConfig;

        return LocalDevelopmentKey();
    }

    private static string? _cachedKey;
    private static readonly object _keyLock = new();

    private static string LocalDevelopmentKey()
    {
        if (_cachedKey is not null) return _cachedKey;

        lock (_keyLock)
        {
            if (_cachedKey is not null) return _cachedKey;

            var path = Path.Combine(AppContext.BaseDirectory, "jwt-key.local.txt");

            if (File.Exists(path))
            {
                var existing = File.ReadAllText(path).Trim();
                if (existing.Length >= 32)
                {
                    _cachedKey = existing;
                    return _cachedKey;
                }
            }

            var generated = Convert.ToBase64String(
                System.Security.Cryptography.RandomNumberGenerator.GetBytes(48));

            try { File.WriteAllText(path, generated); }
            catch { /* read-only location: fall back to an in-memory key */ }

            _cachedKey = generated;
            return _cachedKey;
        }
    }
}
