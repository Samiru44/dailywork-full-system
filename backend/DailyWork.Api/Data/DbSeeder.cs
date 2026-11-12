using DailyWork.Api.Models;

namespace DailyWork.Api.Data;

/// <summary>
/// Creates the starting data for an empty database: the job categories, a
/// default administrator, and a small set of clearly-labelled demonstration
/// accounts and job postings so the system can be shown working.
///
/// Every demonstration account uses an @dailywork.lk address. The public
/// statistics endpoint uses that to report honestly whether the figures a
/// visitor sees are still only demonstration data.
/// </summary>
public static class DbSeeder
{
    public static void Seed(
        AppDbContext db,
        bool includeDemoAccounts = true,
        string? adminName = null,
        string? adminEmail = null,
        string? adminPhone = null,
        string? adminPassword = null)
    {
        SeedCategories(db);

        if (includeDemoAccounts)
        {
            SeedUsersAndJobs(db);
            return;
        }

        // Never create the documented demo administrator in production. A
        // production admin is created only when the owner supplies a private
        // email and password through environment variables on first startup.
        if (db.Users.Any() || string.IsNullOrWhiteSpace(adminEmail) ||
            string.IsNullOrWhiteSpace(adminPassword))
            return;

        if (adminPassword.Length < 12)
            throw new InvalidOperationException(
                "DAILYWORK_ADMIN_PASSWORD must contain at least 12 characters.");

        db.Users.Add(new User
        {
            Name = string.IsNullOrWhiteSpace(adminName) ? "DailyWork Administrator" : adminName.Trim(),
            Email = adminEmail.Trim(),
            Phone = string.IsNullOrWhiteSpace(adminPhone) ? "" : adminPhone.Trim(),
            Role = "admin",
            District = "",
            VerificationStatus = "verified",
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(adminPassword)
        });
        db.SaveChanges();
    }

    // =================================================================

    private static void SeedCategories(AppDbContext db)
    {
        if (db.JobCategories.Any()) return;

        db.JobCategories.AddRange(
            new JobCategory { Name = "Construction",      Icon = "fa-helmet-safety", SortOrder = 1, Description = "Building sites, masonry, painting and finishing work." },
            new JobCategory { Name = "Agriculture",       Icon = "fa-seedling",      SortOrder = 2, Description = "Farming, harvesting and estate work." },
            new JobCategory { Name = "Manufacturing",     Icon = "fa-industry",      SortOrder = 3, Description = "Factory, warehouse and production line work." },
            new JobCategory { Name = "Transportation",    Icon = "fa-truck",         SortOrder = 4, Description = "Driving, loading and delivery work." },
            new JobCategory { Name = "Domestic Services", Icon = "fa-house",         SortOrder = 5, Description = "Housekeeping, cooking and household help." },
            new JobCategory { Name = "Cleaning",          Icon = "fa-broom",         SortOrder = 6, Description = "Office, site and commercial cleaning." },
            new JobCategory { Name = "Security",          Icon = "fa-shield-halved", SortOrder = 7, Description = "Site security and night watch duties." },
            new JobCategory { Name = "Hospitality",       Icon = "fa-utensils",      SortOrder = 8, Description = "Hotel, restaurant and event work." }
        );

        db.SaveChanges();
    }

    private static void SeedUsersAndJobs(AppDbContext db)
    {
        if (db.Users.Any()) return;

        // ---------- administrator ----------
        // The starting password is published in the setup instructions and must
        // be changed on a real deployment; it is not a secret.
        var admin = new User
        {
            Name = "System Administrator",
            Email = "admin@dailywork.lk",
            Phone = "0770000000",
            Role = "admin",
            District = "Colombo",
            PasswordHash = BCrypt.Net.BCrypt.HashPassword("Admin@12345")
        };

        // ---------- demonstration workers ----------
        var workers = new List<User>
        {
            NewWorker("Nimal Perera",   "worker@dailywork.lk",  "0777654321", "Colombo",
                      "Masonry, Painting, Construction", "Colombo", 8,
                      "Eight years on housing and commercial sites across the Western Province.",
                      "NVQ Level 3 Masonry"),

            NewWorker("Sunil Bandara",  "sunil@dailywork.lk",   "0771112222", "Gampaha",
                      "Driving, Delivery, Loading", "Gampaha", 5,
                      "Five years of lorry and van delivery work.",
                      "Light vehicle licence"),

            NewWorker("Kamala Silva",   "kamala@dailywork.lk",  "0773334444", "Colombo",
                      "Cleaning, Housekeeping", "Colombo", 3,
                      "Three years of office and household cleaning.", ""),
        };

        // ---------- demonstration employers ----------
        var employers = new List<User>
        {
            NewEmployer("Kasun Fernando",  "employer@dailywork.lk",   "0771234567", "Colombo"),
            NewEmployer("Lanka Logistics", "logistics@dailywork.lk",  "0112345001", "Gampaha"),
            NewEmployer("CleanCo",         "cleanco@dailywork.lk",    "0112345002", "Colombo"),
            NewEmployer("Green Farms",     "farms@dailywork.lk",      "0112345003", "Kurunegala"),
            NewEmployer("QuickMove",       "quickmove@dailywork.lk",  "0112345004", "Negombo"),
            NewEmployer("BuildRight",      "buildright@dailywork.lk", "0112345005", "Kandy"),
            NewEmployer("SafeGuard",       "safeguard@dailywork.lk",  "0112345006", "Colombo"),
            NewEmployer("HomeCare",        "homecare@dailywork.lk",   "0112345007", "Negombo"),
            NewEmployer("ColorPro",        "colorpro@dailywork.lk",   "0112345008", "Galle"),
            NewEmployer("Hill Estates",    "hill@dailywork.lk",       "0112345009", "Nuwara Eliya"),
            NewEmployer("Pettah Traders",  "pettah@dailywork.lk",     "0112345010", "Colombo"),
            NewEmployer("GarmentPlus",     "garment@dailywork.lk",    "0112345011", "Katunayake"),
        };

        // A verified organization, so the verified badge can be demonstrated
        // against an account that genuinely went through approval.
        var organization = new User
        {
            Name = "Ceylon Infrastructure (Pvt) Ltd",
            Email = "organization@dailywork.lk",
            Phone = "0112345020",
            Role = "organization",
            District = "Colombo",
            Location = "Colombo",
            OrganizationName = "Ceylon Infrastructure (Pvt) Ltd",
            RegistrationNumber = "PV-00123456",
            OrganizationAddress = "42 Galle Road, Colombo 03",
            OrganizationWebsite = "https://example.lk",
            VerificationStatus = "verified",
            VerificationRequestedAt = DateTime.UtcNow.AddDays(-20),
            VerifiedAt = DateTime.UtcNow.AddDays(-18),
            PasswordHash = BCrypt.Net.BCrypt.HashPassword("Password@123")
        };

        // One organization left waiting, so the admin verification queue is not
        // empty the first time it is opened.
        var pendingOrg = new User
        {
            Name = "Lanka Agro Services",
            Email = "agro@dailywork.lk",
            Phone = "0112345021",
            Role = "organization",
            District = "Kurunegala",
            Location = "Kurunegala",
            OrganizationName = "Lanka Agro Services",
            RegistrationNumber = "PV-00987654",
            OrganizationAddress = "118 Kandy Road, Kurunegala",
            VerificationStatus = "pending",
            VerificationNotes = "Registered agricultural labour supplier since 2019.",
            VerificationRequestedAt = DateTime.UtcNow.AddDays(-2),
            PasswordHash = BCrypt.Net.BCrypt.HashPassword("Password@123")
        };

        db.Users.Add(admin);
        db.Users.AddRange(workers);
        db.Users.AddRange(employers);
        db.Users.Add(organization);
        db.Users.Add(pendingOrg);
        db.SaveChanges();

        // The seeded administrator is verified by the system itself.
        organization.VerifiedByUserId = admin.Id;

        int E(string name) => employers.First(e => e.Name == name).Id;

        db.Jobs.AddRange(new List<Job>
        {
            NewJob("Construction Helper",    "Construction",      "Colombo",      "Colombo",      2500, E("Kasun Fernando"),
                   "Assist masons on a housing site. Daily pay, meals provided.", "Construction, Masonry", urgent: true, days: 10),

            NewJob("Warehouse Worker",       "Manufacturing",     "Gampaha",      "Gampaha",      1900, E("Lanka Logistics"),
                   "Loading and sorting in a dry goods warehouse.", "Loading, Warehouse", days: 20),

            NewJob("Office Cleaner",         "Cleaning",          "Colombo",      "Colombo",      1500, E("CleanCo"),
                   "Office cleaning, morning shift.", "Cleaning, Housekeeping", days: 22),

            NewJob("Farm Worker",            "Agriculture",       "Kurunegala",   "Kurunegala",   1700, E("Green Farms"),
                   "Seasonal harvesting work.", "Farming, Agriculture", days: 15),

            NewJob("Delivery Assistant",     "Transportation",    "Negombo",      "Gampaha",      2000, E("QuickMove"),
                   "Help with lorry deliveries around Negombo.", "Delivery, Loading, Driving", urgent: true, days: 12),

            NewJob("Experienced Mason",      "Construction",      "Kandy",        "Kandy",        3200, E("BuildRight"),
                   "Experienced mason for a two-week project.", "Masonry, Construction", days: 14, workers: 2),

            NewJob("Security Guard (Night)", "Security",          "Colombo",      "Colombo",      2200, E("SafeGuard"),
                   "Night shift at a retail complex.", "Security", per: "shift", days: 30),

            NewJob("Housekeeper",            "Domestic Services", "Negombo",      "Gampaha",      1600, E("HomeCare"),
                   "Housekeeping, five days a week.", "Housekeeping, Cleaning", days: 20),

            NewJob("Painter",                "Construction",      "Galle",        "Galle",        2800, E("ColorPro"),
                   "Interior painting job, tools provided.", "Painting", urgent: true, days: 8),

            NewJob("Tea Plucker",            "Agriculture",       "Nuwara Eliya", "Nuwara Eliya", 1400, E("Hill Estates"),
                   "Estate work, accommodation available.", "Farming, Agriculture", days: 25, workers: 5),

            NewJob("Loading Helper",         "Transportation",    "Colombo",      "Colombo",      1800, E("Pettah Traders"),
                   "Pettah market loading work, early mornings.", "Loading", days: 18),

            NewJob("Machine Operator",       "Manufacturing",     "Katunayake",   "Gampaha",      2600, E("GarmentPlus"),
                   "Garment factory machine operation. Experience preferred.", "Manufacturing, Machine operation", days: 24),

            NewJob("Site Supervisor Support","Construction",      "Colombo",      "Colombo",      3000, organization.Id,
                   "Support the site supervisor on a road project.", "Construction, Masonry", days: 30, workers: 3),
        });

        db.SaveChanges();

        // A welcome notification for each demonstration worker.
        foreach (var w in workers)
        {
            db.Notifications.Add(new Notification
            {
                UserId = w.Id,
                Type = "system",
                Title = "Welcome to DailyWork",
                Message = "Your profile is set up. Check your recommended jobs to find work that suits your skills."
            });
        }

        db.SaveChanges();
    }

    // =================================================================

    private static User NewWorker(string name, string email, string phone, string location,
                                  string skills, string district, int years, string experience,
                                  string certifications) => new()
    {
        Name = name,
        Email = email,
        Phone = phone,
        Role = "worker",
        Location = location,
        District = district,
        Skills = skills,
        Experience = experience,
        ExperienceYears = years,
        Certifications = certifications,
        Available = true,
        PasswordHash = BCrypt.Net.BCrypt.HashPassword("Password@123")
    };

    private static User NewEmployer(string name, string email, string phone, string district) => new()
    {
        Name = name,
        Email = email,
        Phone = phone,
        Role = "employer",
        Location = district,
        District = district,
        Bio = "Employer on DailyWork.",

        // Not verified: the badge only appears after an administrator approves.
        VerificationStatus = "unverified",
        PasswordHash = BCrypt.Net.BCrypt.HashPassword("Password@123")
    };

    private static Job NewJob(string title, string category, string location, string district,
                              decimal pay, int employerId, string description, string skills,
                              bool urgent = false, string per = "day", int days = 7, int workers = 1) => new()
    {
        Title = title,
        Category = category,
        Location = location,
        District = district,
        Pay = pay,
        Per = per,
        Urgent = urgent,
        EmployerId = employerId,
        Description = description,
        RequiredSkills = skills,
        WorkersNeeded = workers,
        ExpectedUnits = days,
        StartDate = DateTime.UtcNow.Date.AddDays(1),
        EndDate = DateTime.UtcNow.Date.AddDays(days)
    };
}
