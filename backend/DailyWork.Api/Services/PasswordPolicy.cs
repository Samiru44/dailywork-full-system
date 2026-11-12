namespace DailyWork.Api.Services;

/// <summary>
/// Password rules, kept in one place so registration and any future password
/// change screen enforce exactly the same thing.
/// </summary>
public static class PasswordPolicy
{
    public const int MinimumLength = 8;

    private static readonly string[] TooCommon =
    {
        "password", "12345678", "123456789", "qwerty123", "password1",
        "11111111", "abc12345", "dailywork", "letmein1", "admin123"
    };

    /// <summary>Returns null when the password is acceptable, or the reason it is not.</summary>
    public static string? Validate(string? password, string? email = null, string? name = null)
    {
        if (string.IsNullOrWhiteSpace(password))
            return "Please enter a password.";

        if (password.Length < MinimumLength)
            return $"Password must be at least {MinimumLength} characters long.";

        if (password.Length > 128)
            return "Password must be shorter than 128 characters.";

        if (!password.Any(char.IsLetter))
            return "Password must contain at least one letter.";

        if (!password.Any(char.IsDigit))
            return "Password must contain at least one number.";

        if (TooCommon.Contains(password.ToLowerInvariant()))
            return "That password is too easy to guess. Please choose another one.";

        if (!string.IsNullOrWhiteSpace(email))
        {
            var localPart = email.Split('@')[0];
            if (localPart.Length >= 4 &&
                password.Contains(localPart, StringComparison.OrdinalIgnoreCase))
                return "Password must not contain your email address.";
        }

        if (!string.IsNullOrWhiteSpace(name) && name.Trim().Length >= 4 &&
            password.Contains(name.Trim(), StringComparison.OrdinalIgnoreCase))
            return "Password must not contain your name.";

        return null;
    }
}
