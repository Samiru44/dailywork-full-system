using System.Net;
using System.Net.Mail;
using System.Net.Mime;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;

namespace DailyWork.Api.Services;

/// <summary>
/// Sends the emails waiting in EmailQueue, one at a time, in the background.
///
/// Uses SMTP for local development or Brevo's HTTPS transactional email API
/// for hosted services that block outbound SMTP ports.
/// </summary>
public class EmailDispatcher : BackgroundService
{
    private readonly EmailQueue _queue;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<EmailDispatcher> _log;

    public EmailDispatcher(
        EmailQueue queue,
        IHttpClientFactory httpClientFactory,
        ILogger<EmailDispatcher> log)
    {
        _queue = queue;
        _httpClientFactory = httpClientFactory;
        _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            await foreach (var message in _queue.Reader.ReadAllAsync(stoppingToken))
            {
                try
                {
                    await DeliverAsync(message, stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch (Exception ex)
                {
                    // One bad address or a mail-server hiccup must not stop
                    // the emails behind it. Log it and move on.
                    _log.LogError(ex,
                        "Email delivery failed for \"{Subject}\" to {To}. Check the configured provider, sender verification, API/SMTP credentials and recipient address. Secrets are intentionally not logged.",
                        message.Subject, message.To);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // The application is shutting down.
        }
    }

    private async Task DeliverAsync(EmailMessage message, CancellationToken stoppingToken)
    {
        var settings = _queue.Settings;

        // The demonstration accounts use a made-up domain, so nothing is ever
        // really sent to them. Their messages go to the outbox folder instead.
        var delivery = _queue.DeliveryFor(message.To);

        if (delivery == EmailDelivery.Off)
        {
            _log.LogInformation("Email not sent (demonstration address): \"{Subject}\" to {To}",
                message.Subject, message.To);
            return;
        }

        var toOutbox = delivery == EmailDelivery.Outbox;

        var fromAddress = _queue.FromAddress.Contains('@')
            ? _queue.FromAddress
            : "no-reply@dailywork.local";

        if (delivery == EmailDelivery.BrevoApi)
        {
            await DeliverViaBrevoApiAsync(message, fromAddress, stoppingToken);
            _log.LogInformation("Email sent through Brevo API: \"{Subject}\" to {To}",
                message.Subject, message.To);
            return;
        }

        using var mail = new MailMessage();
        mail.From = new MailAddress(fromAddress, settings.FromName);
        mail.To.Add(new MailAddress(message.To.Trim(), EmailRenderer.OneLine(message.ToName)));
        mail.Subject = EmailRenderer.OneLine(message.Subject);
        mail.SubjectEncoding = Encoding.UTF8;

        // Plain text for mail programs that do not show HTML, with the HTML
        // version alongside it.
        mail.Body = EmailRenderer.Text(message, settings.SiteUrl);
        mail.BodyEncoding = Encoding.UTF8;
        mail.IsBodyHtml = false;
        mail.AlternateViews.Add(AlternateView.CreateAlternateViewFromString(
            EmailRenderer.Html(message, settings.SiteUrl), Encoding.UTF8, MediaTypeNames.Text.Html));

        foreach (var file in message.Attachments)
        {
            mail.Attachments.Add(
                new Attachment(new MemoryStream(file.Data), file.FileName, file.ContentType));
        }

        using var client = new SmtpClient();

        if (toOutbox)
        {
            client.DeliveryMethod = SmtpDeliveryMethod.SpecifiedPickupDirectory;
            client.PickupDirectoryLocation = _queue.OutboxPath;
        }
        else
        {
            client.DeliveryMethod = SmtpDeliveryMethod.Network;
            client.Host = settings.Host.Trim();
            client.Port = settings.Port;
            client.EnableSsl = settings.EnableSsl;

            if (!string.IsNullOrWhiteSpace(settings.Username))
                client.Credentials = new NetworkCredential(settings.Username.Trim(), settings.Password);
        }

        // Give up on a mail server that does not answer, rather than letting
        // one stuck message hold up every email behind it.
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        limit.CancelAfter(TimeSpan.FromSeconds(30));

        await client.SendMailAsync(mail, limit.Token);

        if (toOutbox)
            _log.LogInformation("Email saved to the outbox folder: \"{Subject}\" to {To}",
                message.Subject, message.To);
        else
            _log.LogInformation("Email sent: \"{Subject}\" to {To}", message.Subject, message.To);
    }

    private async Task DeliverViaBrevoApiAsync(
        EmailMessage message, string fromAddress, CancellationToken stoppingToken)
    {
        var settings = _queue.Settings;
        var payload = new Dictionary<string, object?>
        {
            ["sender"] = new { email = fromAddress, name = settings.FromName },
            ["to"] = new[]
            {
                new { email = message.To.Trim(), name = EmailRenderer.OneLine(message.ToName) }
            },
            ["subject"] = EmailRenderer.OneLine(message.Subject),
            ["textContent"] = EmailRenderer.Text(message, settings.SiteUrl),
            ["htmlContent"] = EmailRenderer.Html(message, settings.SiteUrl)
        };

        if (message.Attachments.Count > 0)
        {
            payload["attachment"] = message.Attachments.Select(file => new
            {
                content = Convert.ToBase64String(file.Data),
                name = Path.GetFileName(file.FileName)
            }).ToArray();
        }

        using var request = new HttpRequestMessage(
            HttpMethod.Post, "https://api.brevo.com/v3/smtp/email");
        request.Headers.Add("api-key", settings.ApiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = JsonContent.Create(payload);

        using var limit = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        limit.CancelAfter(TimeSpan.FromSeconds(30));

        var client = _httpClientFactory.CreateClient();
        using var response = await client.SendAsync(request, limit.Token);
        if (!response.IsSuccessStatusCode)
        {
            var responseText = await response.Content.ReadAsStringAsync(limit.Token);
            if (responseText.Length > 800) responseText = responseText[..800];
            throw new HttpRequestException(
                $"Brevo API returned HTTP {(int)response.StatusCode} ({response.StatusCode}): {responseText}");
        }
    }
}

/// <summary>
/// Turns an EmailMessage into its two bodies. Everything a user typed is
/// HTML-encoded here, so a job title or applicant message can never inject
/// markup into somebody else's inbox.
/// </summary>
public static class EmailRenderer
{
    private const string Footer1 = "DailyWork - Work Today, Earn Today";
    private const string Footer2 = "You are receiving this email because you have a DailyWork account.";

    /// <summary>Removes line breaks, which are not allowed in an email subject or name.</summary>
    public static string OneLine(string? value) =>
        (value ?? "").Replace("\r", " ").Replace("\n", " ").Trim();

    private static string Link(string? siteUrl, string? path)
    {
        var site = (siteUrl ?? "").Trim().TrimEnd('/');
        if (string.IsNullOrWhiteSpace(path)) return "";

        if (!site.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
            !site.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            return "";

        return site + path;
    }

    public static string Text(EmailMessage message, string? siteUrl)
    {
        var text = new StringBuilder();

        if (!string.IsNullOrWhiteSpace(message.Heading))
        {
            text.AppendLine(message.Heading);
            text.AppendLine();
        }

        foreach (var paragraph in message.Paragraphs)
        {
            text.AppendLine(paragraph);
            text.AppendLine();
        }

        var printed = 0;
        foreach (var (label, value) in message.Details)
        {
            if (string.IsNullOrWhiteSpace(value)) continue;
            text.AppendLine(label + ": " + value);
            printed++;
        }
        if (printed > 0) text.AppendLine();

        var link = Link(siteUrl, message.ActionPath);
        if (link.Length > 0)
        {
            text.AppendLine(message.ActionText + ": " + link);
            text.AppendLine();
        }

        text.AppendLine(Footer1);
        text.AppendLine(Footer2);
        return text.ToString();
    }

    public static string Html(EmailMessage message, string? siteUrl)
    {
        static string Encode(string? value) =>
            WebUtility.HtmlEncode(value ?? "").Replace("\r\n", "\n").Replace("\n", "<br>");

        var html = new StringBuilder();

        html.Append("<!DOCTYPE html><html><body style='margin:0;padding:0;background:#f6f9fd;'>");
        html.Append("<table role='presentation' width='100%' cellpadding='0' cellspacing='0' ");
        html.Append("style='background:#f6f9fd;padding:24px 0;font-family:Segoe UI,Arial,sans-serif;color:#1e293b;'>");
        html.Append("<tr><td align='center'>");
        html.Append("<table role='presentation' width='600' cellpadding='0' cellspacing='0' ");
        html.Append("style='max-width:600px;width:100%;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;'>");

        // Brand bar
        html.Append("<tr><td style='background:#0b2447;border-radius:12px 12px 0 0;padding:18px 28px;'>");
        html.Append("<span style='font-size:20px;font-weight:700;color:#ffffff;'>Daily");
        html.Append("<span style='color:#4ade80;'>Work</span></span></td></tr>");

        html.Append("<tr><td style='padding:28px;font-size:15px;line-height:1.6;'>");

        if (!string.IsNullOrWhiteSpace(message.Heading))
        {
            html.Append("<h1 style='margin:0 0 16px;font-size:20px;color:#0b2447;'>");
            html.Append(Encode(message.Heading));
            html.Append("</h1>");
        }

        foreach (var paragraph in message.Paragraphs)
        {
            html.Append("<p style='margin:0 0 14px;'>");
            html.Append(Encode(paragraph));
            html.Append("</p>");
        }

        var rows = message.Details.Where(d => !string.IsNullOrWhiteSpace(d.Value)).ToList();
        if (rows.Count > 0)
        {
            html.Append("<table role='presentation' width='100%' cellpadding='0' cellspacing='0' ");
            html.Append("style='margin:6px 0 18px;border-top:1px solid #e2e8f0;font-size:14px;'>");

            foreach (var (label, value) in rows)
            {
                html.Append("<tr><td style='padding:9px 12px 9px 0;border-bottom:1px solid #e2e8f0;");
                html.Append("color:#64748b;width:38%;vertical-align:top;'>");
                html.Append(Encode(label));
                html.Append("</td><td style='padding:9px 0;border-bottom:1px solid #e2e8f0;vertical-align:top;'>");
                html.Append(Encode(value));
                html.Append("</td></tr>");
            }

            html.Append("</table>");
        }

        var link = Link(siteUrl, message.ActionPath);
        if (link.Length > 0)
        {
            html.Append("<p style='margin:20px 0 6px;'><a href='");
            html.Append(WebUtility.HtmlEncode(link));
            html.Append("' style='display:inline-block;background:#1565d8;color:#ffffff;text-decoration:none;");
            html.Append("font-weight:600;padding:11px 22px;border-radius:8px;'>");
            html.Append(Encode(message.ActionText));
            html.Append("</a></p>");
        }

        html.Append("</td></tr>");

        html.Append("<tr><td style='padding:16px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;'>");
        html.Append(Encode(Footer1));
        html.Append("<br>");
        html.Append(Encode(Footer2));
        html.Append("</td></tr>");

        html.Append("</table></td></tr></table></body></html>");
        return html.ToString();
    }
}
