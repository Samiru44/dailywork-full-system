using System.Globalization;
using DailyWork.Api.Models;

namespace DailyWork.Api.Services;

/// <summary>
/// The wording of every email the system sends, kept in one place.
///
/// Each method only describes the message (who it is for, what it says). The
/// HTML is built later by EmailRenderer, which also escapes anything a user
/// typed, so nothing here needs to worry about markup.
/// </summary>
public static class EmailTemplates
{
    private const string Dashboard = "/#/dashboard";

    // -----------------------------------------------------------------
    // Shared wording
    // -----------------------------------------------------------------

    public static string Money(decimal amount) =>
        "Rs. " + amount.ToString("#,##0.##", CultureInfo.InvariantCulture);

    private static string Pay(Job job) => Money(job.Pay) + " per " + job.Per;

    private static string Day(DateTime date) =>
        date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);

    private static string Dates(Job job)
    {
        if (job.StartDate.HasValue && job.EndDate.HasValue)
            return Day(job.StartDate.Value) + " to " + Day(job.EndDate.Value);
        if (job.StartDate.HasValue) return "From " + Day(job.StartDate.Value);
        if (job.EndDate.HasValue) return "Until " + Day(job.EndDate.Value);
        return "";
    }

    private static string Place(Job job) =>
        string.IsNullOrWhiteSpace(job.District) ||
        job.District.Equals(job.Location, StringComparison.OrdinalIgnoreCase)
            ? job.Location
            : job.Location + ", " + job.District;

    private static string Experience(User worker)
    {
        var years = worker.ExperienceYears > 0
            ? worker.ExperienceYears + (worker.ExperienceYears == 1 ? " year" : " years")
            : "";

        if (string.IsNullOrWhiteSpace(worker.Experience)) return years;
        return years.Length > 0 ? years + " - " + worker.Experience : worker.Experience;
    }

    // -----------------------------------------------------------------
    // A worker applies for a job
    // -----------------------------------------------------------------

    /// <summary>To the worker: confirmation that their application went in.</summary>
    public static EmailMessage ApplicationReceived(User worker, Job job, string employerName, string? cvFileName)
    {
        return new EmailMessage
        {
            To = worker.Email,
            ToName = worker.Name,
            Subject = "Application sent: " + job.Title,
            Heading = "Your application was sent",
            Paragraphs = new List<string>
            {
                "Hello " + worker.Name + ",",
                "Your application for \"" + job.Title + "\" has been sent to " + employerName +
                ". You will get another email when they make a decision."
            },
            Details = new List<(string Label, string Value)>
            {
                ("Job", job.Title),
                ("Employer", employerName),
                ("Location", Place(job)),
                ("Wage", Pay(job)),
                ("Dates", Dates(job)),
                ("Your CV", string.IsNullOrWhiteSpace(cvFileName)
                    ? "Not included. You have no CV on your profile yet - you can add one under My Profile."
                    : "Included with your application (" + cvFileName + ")")
            },
            ActionText = "View my applications",
            ActionPath = Dashboard
        };
    }

    /// <summary>To the employer: who applied, with the CV attached when there is one.</summary>
    public static EmailMessage NewApplicant(User employer, User worker, Job job, string? note, CvDocument? cv)
    {
        var message = new EmailMessage
        {
            To = employer.Email,
            ToName = employer.Name,
            Subject = "New applicant for " + job.Title + ": " + worker.Name,
            Heading = "You have a new applicant",
            Paragraphs = new List<string>
            {
                "Hello " + employer.Name + ",",
                worker.Name + " has applied for your job \"" + job.Title + "\". " +
                (cv is null
                    ? "They have not uploaded a CV."
                    : "Their CV is attached to this email."),
                "Sign in to shortlist, hire or decline this applicant."
            },
            Details = new List<(string Label, string Value)>
            {
                ("Applicant", worker.Name),
                ("Phone", worker.Phone),
                ("Email", worker.Email),
                ("Location", string.IsNullOrWhiteSpace(worker.District) ? worker.Location : worker.District),
                ("Skills", worker.Skills),
                ("Experience", Experience(worker)),
                ("Certifications", worker.Certifications),
                ("Message", (note ?? "").Trim())
            },
            ActionText = "Review applicants",
            ActionPath = Dashboard
        };

        if (cv is not null && cv.Data.Length > 0)
        {
            message.Attachments.Add(new EmailAttachment
            {
                FileName = cv.FileName,
                ContentType = cv.ContentType,
                Data = cv.Data
            });
        }

        return message;
    }

    // -----------------------------------------------------------------
    // The employer decides on an application
    // -----------------------------------------------------------------

    /// <summary>
    /// To the worker: shortlisted, hired, declined, or work verified.
    /// Returns null for a status that has no email.
    /// </summary>
    public static EmailMessage? ApplicationStatus(User worker, Job job, User? employer, string status)
    {
        var employerName = employer?.Name ?? "the employer";

        string subject, heading, body;

        switch (status)
        {
            case "shortlisted":
                subject = "You have been shortlisted: " + job.Title;
                heading = "You have been shortlisted";
                body = employerName + " has shortlisted your application for \"" + job.Title +
                       "\". They have not made a final decision yet - you will be told when they do.";
                break;

            case "accepted":
                subject = "You have been hired: " + job.Title;
                heading = "You have been hired";
                body = employerName + " has selected you for \"" + job.Title +
                       "\". Their contact details are below so you can agree where and when to start.";
                break;

            case "rejected":
                subject = "Update on your application: " + job.Title;
                heading = "Application not successful";
                body = "Your application for \"" + job.Title + "\" was not successful this time. " +
                       "There are other jobs that match your profile on your dashboard.";
                break;

            case "completed":
                subject = "Work verified: " + job.Title;
                heading = "Your work has been verified";
                body = employerName + " has confirmed that your work on \"" + job.Title +
                       "\" is complete, and a payment record has been raised. " +
                       "When the money reaches you, confirm it under Payments on your dashboard.";
                break;

            default:
                return null;
        }

        var details = new List<(string Label, string Value)>
        {
            ("Job", job.Title),
            ("Employer", employerName),
            ("Location", Place(job)),
            ("Wage", Pay(job))
        };

        // Contact details are only passed on once the worker has been hired.
        if (status == "accepted")
        {
            details.Add(("Employer phone", employer?.Phone ?? ""));
            details.Add(("Employer email", employer?.Email ?? ""));
            details.Add(("Dates", Dates(job)));
        }

        return new EmailMessage
        {
            To = worker.Email,
            ToName = worker.Name,
            Subject = subject,
            Heading = heading,
            Paragraphs = new List<string> { "Hello " + worker.Name + ",", body },
            Details = details,
            ActionText = status == "rejected" ? "Find more jobs" : "Open my dashboard",
            ActionPath = status == "rejected" ? "/#/jobs" : Dashboard
        };
    }

    // -----------------------------------------------------------------
    // A job is posted
    // -----------------------------------------------------------------

    /// <summary>To the employer: confirmation that their posting is live.</summary>
    public static EmailMessage JobPosted(User employer, Job job, int workersNotified)
    {
        var reach = workersNotified switch
        {
            0 => "No workers match it closely yet, but it is visible to everyone searching for jobs.",
            1 => "1 worker whose profile matches it has been told about it.",
            _ => workersNotified + " workers whose profiles match it have been told about it."
        };

        return new EmailMessage
        {
            To = employer.Email,
            ToName = employer.Name,
            Subject = "Your job is live: " + job.Title,
            Heading = "Your job has been posted",
            Paragraphs = new List<string>
            {
                "Hello " + employer.Name + ",",
                "\"" + job.Title + "\" is now open for applications. " + reach,
                "You will get an email each time somebody applies."
            },
            Details = new List<(string Label, string Value)>
            {
                ("Job", job.Title),
                ("Category", job.Category),
                ("Location", Place(job)),
                ("Wage", Pay(job)),
                ("Workers needed", job.WorkersNeeded.ToString(CultureInfo.InvariantCulture)),
                ("Skills asked for", job.RequiredSkills),
                ("Dates", Dates(job))
            },
            ActionText = "Manage my jobs",
            ActionPath = Dashboard
        };
    }

    /// <summary>To a worker whose profile matches a newly posted job.</summary>
    public static EmailMessage JobMatch(string workerName, string workerEmail, Job job, string employerName)
    {
        return new EmailMessage
        {
            To = workerEmail,
            ToName = workerName,
            Subject = "New job that matches your profile: " + job.Title,
            Heading = "A new job matches your profile",
            Paragraphs = new List<string>
            {
                "Hello " + workerName + ",",
                employerName + " has just posted \"" + job.Title +
                "\", which matches the skills and area on your profile."
            },
            Details = new List<(string Label, string Value)>
            {
                ("Job", job.Title),
                ("Employer", employerName),
                ("Category", job.Category),
                ("Location", Place(job)),
                ("Wage", Pay(job)),
                ("Workers needed", job.WorkersNeeded.ToString(CultureInfo.InvariantCulture)),
                ("Dates", Dates(job))
            },
            ActionText = "View the job",
            ActionPath = "/#/job?id=" + job.Id.ToString(CultureInfo.InvariantCulture)
        };
    }

    // -----------------------------------------------------------------
    // Reports
    // -----------------------------------------------------------------

    /// <summary>To the person who asked for it: their own report, with the figures as a CSV file.</summary>
    public static EmailMessage Report(User user, string title, List<(string Label, string Value)> figures,
                                      List<EmailAttachment> files)
    {
        var today = Day(DateTime.UtcNow);

        return new EmailMessage
        {
            To = user.Email,
            ToName = user.Name,
            Subject = title + " - " + today,
            Heading = title,
            Paragraphs = new List<string>
            {
                "Hello " + user.Name + ",",
                "Here is the report you asked for, as it stood on " + today + "." +
                (files.Count > 0 ? " The detailed records are attached as a spreadsheet (CSV) file." : "")
            },
            Details = figures,
            ActionText = "Open the full report",
            ActionPath = Dashboard,
            Attachments = files
        };
    }
}
