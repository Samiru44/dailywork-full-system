namespace DailyWork.Api.Models;

/// <summary>
/// A worker's uploaded CV (one per account).
///
/// The file is kept in its own table rather than as columns on Users. Users is
/// read on almost every request, and a CV can be a couple of megabytes; keeping
/// the bytes here means they are only ever loaded when somebody actually
/// downloads the file or it is attached to an application email.
/// </summary>
public class CvDocument
{
    public int Id { get; set; }

    public int UserId { get; set; }
    public User? User { get; set; }

    /// <summary>The name the worker's file had, cleaned of any path.</summary>
    public string FileName { get; set; } = "";

    /// <summary>Decided by the server from the file type, never taken from the browser.</summary>
    public string ContentType { get; set; } = "";

    public long SizeBytes { get; set; }

    public byte[] Data { get; set; } = Array.Empty<byte>();

    public DateTime UploadedAt { get; set; } = DateTime.UtcNow;
}
