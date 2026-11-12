using System.Collections.Concurrent;
using System.Threading.Channels;
using Microsoft.Extensions.Options;

namespace DailyWork.Api.Services;

/// <summary>
/// Email settings. Read from the "Smtp" section of appsettings.json, or from
/// environment variables named Smtp__Host, Smtp__Port, Smtp__Username,
/// Smtp__Password and Smtp__From (two underscores).
///
/// The password belongs in an environment variable, not in appsettings.json,
/// so that it is never committed to source control.
/// </summary>
public class SmtpSettings
{
    /// <summary>The mail server, e.g. smtp.gmail.com. Empty means "not configured".</summary>
    public string Host { get; set; } = "";

    /// <summary>587 (STARTTLS) is what almost every provider uses.</summary>
    public int Port { get; set; } = 587;

    public string Username { get; set; } = "";
    public string Password { get; set; } = "";
    public bool EnableSsl { get; set; } = true;

    /// <summary>The address emails come from. Falls back to Username when empty.</summary>
    public string From { get; set; } = "";
    public string FromName { get; set; } = "DailyWork";

    /// <summary>
    /// While no mail server is configured, each email is saved in this folder
    /// as an .eml file instead of being sent, so the feature can be seen
    /// working without an email account. Leave empty to switch that off.
    /// </summary>
    public string OutboxFolder { get; set; } = "";

    /// <summary>The address of the website, used for the links inside emails.</summary>
    public string SiteUrl { get; set; } = "http://localhost:5000";
}

/// <summary>What happens to an email on this installation.</summary>
public enum EmailDelivery
{
    /// <summary>Nothing is configured: emails are only noted in the server log.</summary>
    Off,

    /// <summary>No mail server yet: emails are saved as files in the outbox folder.</summary>
    Outbox,

    /// <summary>A mail server is configured: emails are really sent.</summary>
    Smtp
}

public class EmailAttachment
{
    public string FileName { get; init; } = "";
    public string ContentType { get; init; } = "application/octet-stream";
    public byte[] Data { get; init; } = Array.Empty<byte>();
}

/// <summary>
/// One email, described by its parts rather than as finished HTML. The
/// dispatcher turns the parts into the HTML and plain-text bodies, which keeps
/// the escaping of user-supplied text in a single place.
/// </summary>
public class EmailMessage
{
    public string To { get; init; } = "";
    public string ToName { get; init; } = "";
    public string Subject { get; init; } = "";
    public string Heading { get; init; } = "";
    public List<string> Paragraphs { get; init; } = new();
    public List<(string Label, string Value)> Details { get; init; } = new();

    /// <summary>Text and site path of the button, e.g. "View my applications" and "/#/dashboard".</summary>
    public string ActionText { get; init; } = "";
    public string ActionPath { get; init; } = "";

    public List<EmailAttachment> Attachments { get; init; } = new();
}

/// <summary>
/// Where the rest of the application hands over an email to be sent.
///
/// Controllers call Enqueue and carry on: the message is sent afterwards by
/// EmailDispatcher on a background thread. A slow or failing mail server can
/// therefore never delay a request, and never undo the application, hiring or
/// job posting that caused the email.
/// </summary>
public class EmailQueue
{
    /// <summary>
    /// The seeded demonstration accounts all use this made-up domain. Real
    /// email is never sent to it: the addresses belong to nobody we know.
    /// </summary>
    public const string DemoDomain = "@dailywork.lk";

    // Bounded, so a burst of activity cannot hold an unlimited number of
    // messages (and their attachments) in memory.
    private readonly Channel<EmailMessage> _channel = Channel.CreateBounded<EmailMessage>(200);

    private readonly ConcurrentDictionary<int, DateTime> _lastReport = new();
    private readonly ILogger<EmailQueue> _log;

    public EmailQueue(IOptions<SmtpSettings> options, IWebHostEnvironment env, ILogger<EmailQueue> log)
    {
        _log = log;
        Settings = options.Value;

        var from = string.IsNullOrWhiteSpace(Settings.From) ? Settings.Username : Settings.From;
        FromAddress = (from ?? "").Trim();

        var mode = EmailDelivery.Off;
        var outboxPath = "";

        // The outbox folder is prepared whenever one is named, so that it can
        // also take the messages addressed to demonstration accounts once a
        // real mail server is in use.
        if (!string.IsNullOrWhiteSpace(Settings.OutboxFolder))
        {
            try
            {
                outboxPath = Path.GetFullPath(
                    Path.Combine(env.ContentRootPath, Settings.OutboxFolder.Trim()));
                Directory.CreateDirectory(outboxPath);
                mode = EmailDelivery.Outbox;
            }
            catch (Exception ex)
            {
                outboxPath = "";
                _log.LogWarning(ex, "The email outbox folder could not be created.");
            }
        }

        // A host and From address alone are not enough for Gmail SMTP.
        // Require the authenticated account and its App Password as well;
        // otherwise the app would claim to send mail and fail asynchronously.
        var smtpReady =
            !string.IsNullOrWhiteSpace(Settings.Host) &&
            Settings.Port is >= 1 and <= 65535 &&
            FromAddress.Contains('@') &&
            !string.IsNullOrWhiteSpace(Settings.Username) &&
            !string.IsNullOrWhiteSpace(Settings.Password);

        if (smtpReady)
        {
            mode = EmailDelivery.Smtp;
        }
        else if (!string.IsNullOrWhiteSpace(Settings.Host) ||
                 !string.IsNullOrWhiteSpace(Settings.Username) ||
                 !string.IsNullOrWhiteSpace(Settings.Password))
        {
            _log.LogWarning(
                "SMTP settings are incomplete. Real email is disabled. Configure Smtp:Host, Smtp:Port, Smtp:Username, Smtp:Password and Smtp:From. Current delivery will use the outbox when available.");
        }

        Mode = mode;
        OutboxPath = outboxPath;
    }

    public SmtpSettings Settings { get; }
    public EmailDelivery Mode { get; }
    public string FromAddress { get; }

    /// <summary>Full path of the outbox folder, or empty when there is none.</summary>
    public string OutboxPath { get; }

    public ChannelReader<EmailMessage> Reader => _channel.Reader;

    public static bool IsDemoAddress(string? email) =>
        (email ?? "").Trim().EndsWith(DemoDomain, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// What will actually happen to an email for this address. Mail for a
    /// demonstration account is never sent through the mail server: it goes
    /// to the outbox folder when there is one, and nowhere when there is not.
    /// </summary>
    public EmailDelivery DeliveryFor(string? email)
    {
        if (Mode == EmailDelivery.Smtp && IsDemoAddress(email))
            return OutboxPath.Length > 0 ? EmailDelivery.Outbox : EmailDelivery.Off;

        return Mode;
    }

    /// <summary>One line for the start-up banner, saying what will happen to emails.</summary>
    public string Describe() => Mode switch
    {
        EmailDelivery.Smtp   => $"sending through {Settings.Host} as {FromAddress}",
        EmailDelivery.Outbox => $"no mail server set - emails are saved in {OutboxPath}",
        _                    => "not configured - emails are only noted in this window"
    };

    /// <summary>
    /// Hands a message over for sending. Returns false when it was not queued.
    /// Never throws: a problem with email must not break the caller.
    /// </summary>
    public bool Enqueue(EmailMessage? message)
    {
        try
        {
            if (message is null) return false;

            if (string.IsNullOrWhiteSpace(message.To) || !message.To.Contains('@'))
                return false;

            if (Mode == EmailDelivery.Off)
            {
                _log.LogInformation("Email not sent (email is not configured): \"{Subject}\" to {To}",
                    message.Subject, message.To);
                return false;
            }

            if (_channel.Writer.TryWrite(message)) return true;

            _log.LogWarning("Email queue is full. Dropped \"{Subject}\" to {To}",
                message.Subject, message.To);
            return false;
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "An email could not be queued.");
            return false;
        }
    }

    /// <summary>
    /// A user may email themselves a report once a minute. Stops a held-down
    /// button from using up the mail provider's daily allowance.
    /// </summary>
    public bool TryStartReport(int userId, out int secondsToWait)
    {
        var now = DateTime.UtcNow;
        secondsToWait = 0;

        if (_lastReport.TryGetValue(userId, out var last))
        {
            var elapsed = (now - last).TotalSeconds;
            if (elapsed < 60)
            {
                secondsToWait = (int)Math.Ceiling(60 - elapsed);
                return false;
            }
        }

        _lastReport[userId] = now;
        return true;
    }
}
