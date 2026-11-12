namespace DailyWork.Api.Services;

/// <summary>
/// What the system accepts as a CV: a PDF or Word document of up to 2 MB.
///
/// The browser also checks these before uploading, but that is only for
/// convenience. These are the checks that count, because a request can be
/// sent to the API without going through the website at all.
/// </summary>
public static class CvRules
{
    /// <summary>Largest CV accepted, in bytes (2 MB).</summary>
    public const long MaxBytes = 2 * 1024 * 1024;

    /// <summary>
    /// Largest upload request the server will read at all. A little above
    /// MaxBytes to leave room for the multipart wrapping around the file.
    /// </summary>
    public const long MaxRequestBytes = 3 * 1024 * 1024;

    public const string AllowedTypesText = "PDF or Word document (.pdf, .doc or .docx)";

    private static readonly Dictionary<string, string> ContentTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        [".pdf"]  = "application/pdf",
        [".doc"]  = "application/msword",
        [".docx"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    };

    /// <summary>
    /// The content type to store and serve for a file name, or null when the
    /// file type is not allowed. Decided from the extension here on the
    /// server; whatever type the browser claimed is ignored.
    /// </summary>
    public static string? ContentTypeFor(string fileName) =>
        ContentTypes.TryGetValue(Path.GetExtension(fileName), out var type) ? type : null;

    /// <summary>
    /// True when the file's first bytes are what its extension promises, so a
    /// program or script renamed to "cv.pdf" is refused.
    /// </summary>
    public static bool MatchesItsType(string fileName, byte[] data)
    {
        switch (Path.GetExtension(fileName).ToLowerInvariant())
        {
            case ".pdf":  return StartsWith(data, 0x25, 0x50, 0x44, 0x46);   // %PDF
            case ".docx": return StartsWith(data, 0x50, 0x4B, 0x03, 0x04);   // zip container
            case ".doc":  return StartsWith(data, 0xD0, 0xCF, 0x11, 0xE0);   // legacy Office file
            default:      return false;
        }
    }

    private static bool StartsWith(byte[] data, params byte[] signature)
    {
        if (data.Length < signature.Length) return false;

        for (var i = 0; i < signature.Length; i++)
        {
            if (data[i] != signature[i]) return false;
        }

        return true;
    }

    /// <summary>
    /// Reduces whatever name the browser sent to a plain, safe file name:
    /// no folders, no control characters, and not unreasonably long.
    /// </summary>
    public static string SafeFileName(string? raw)
    {
        // Some browsers send the full path of the file on the user's computer.
        var name = Path.GetFileName((raw ?? "").Replace('\\', '/')).Trim();

        var cleaned = new string(name
            .Where(c => !char.IsControl(c) && c != '"' && c != '<' && c != '>' && c != ':' &&
                        c != '|' && c != '?' && c != '*' && c != ';')
            .ToArray())
            .Trim();

        var extension = Path.GetExtension(cleaned);
        var stem = Path.GetFileNameWithoutExtension(cleaned).Trim();

        if (stem.Length == 0) stem = "cv";
        if (stem.Length > 80) stem = stem.Substring(0, 80).Trim();

        return stem + extension.ToLowerInvariant();
    }
}
