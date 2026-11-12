using System.Security.Claims;
using System.Text;
using DailyWork.Api.Data;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

// Bind to the port assigned by the hosting platform. Locally, keep port 5000.
var portValue = Environment.GetEnvironmentVariable("PORT");
var port = int.TryParse(portValue, out var assignedPort) && assignedPort is > 0 and <= 65535
    ? assignedPort
    : 5000;
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");

// ---------- Database ----------
// SQLite remains the local-development default. Production can select PostgreSQL
// with Database__Provider=PostgreSQL and ConnectionStrings__Default set to an
// Npgsql connection string (Host=...;Database=...;Username=...;Password=...).
var defaultDatabaseProvider = builder.Environment.IsProduction() ? "PostgreSQL" : "Sqlite";
var databaseProvider = builder.Configuration["Database:Provider"] ?? defaultDatabaseProvider;
var databaseConnection = builder.Configuration.GetConnectionString("Default");
if (string.IsNullOrWhiteSpace(databaseConnection))
    throw new InvalidOperationException("ConnectionStrings:Default must be configured.");

builder.Services.AddDbContext<AppDbContext>(options =>
{
    if (databaseProvider.Equals("PostgreSQL", StringComparison.OrdinalIgnoreCase) ||
        databaseProvider.Equals("Postgres", StringComparison.OrdinalIgnoreCase))
    {
        options.UseNpgsql(databaseConnection);
    }
    else if (databaseProvider.Equals("Sqlite", StringComparison.OrdinalIgnoreCase) ||
             databaseProvider.Equals("SQLite", StringComparison.OrdinalIgnoreCase))
    {
        options.UseSqlite(databaseConnection);
    }
    else
    {
        throw new InvalidOperationException(
            $"Unsupported Database:Provider '{databaseProvider}'. Use Sqlite or PostgreSQL.");
    }
});

// ---------- Authentication ----------
// Never allow Production to fall back to an ephemeral local JWT key. On a
// restart, such a fallback would invalidate every active user's session.
var configuredJwtKey = builder.Configuration["DAILYWORK_JWT_KEY"] ??
                       builder.Configuration["Jwt:Key"];
if (builder.Environment.IsProduction() &&
    (string.IsNullOrWhiteSpace(configuredJwtKey) || configuredJwtKey.Length < 32))
{
    throw new InvalidOperationException(
        "Set DAILYWORK_JWT_KEY (at least 32 characters) in the hosting provider's environment settings.");
}
var jwtKey = TokenService.JwtKey(builder.Configuration);

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(opt =>
    {
        opt.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtKey)),
            ClockSkew = TimeSpan.FromMinutes(1)
        };

        opt.Events = new JwtBearerEvents
        {
            // A token stops working the moment the account's privileges change.
            // Without this, a user demoted from admin would keep administrator
            // access until their old token happened to expire.
            OnTokenValidated = async context =>
            {
                var db = context.HttpContext.RequestServices.GetRequiredService<AppDbContext>();

                var idClaim = context.Principal?.FindFirstValue(ClaimTypes.NameIdentifier);
                if (!int.TryParse(idClaim, out var userId))
                {
                    context.Fail("Malformed token.");
                    return;
                }

                var user = await db.Users
                    .AsNoTracking()
                    .FirstOrDefaultAsync(u => u.Id == userId);

                if (user is null || !user.IsActive)
                {
                    context.Fail("This account is no longer active.");
                    return;
                }

                var stampClaim = context.Principal?.FindFirstValue(TokenService.SecurityStampClaim);
                if (!long.TryParse(stampClaim, out var stampTicks) ||
                    stampTicks != user.SecurityStamp.Ticks)
                {
                    context.Fail("Your access has changed. Please sign in again.");
                }
            }
        };
    });

builder.Services.AddAuthorization();

builder.Services.AddScoped<TokenService>();
builder.Services.AddScoped<NotificationService>();
builder.Services.AddScoped<RecommendationService>();
builder.Services.AddSingleton<LoginThrottle>();

// ---------- Email ----------
// Settings come from the "Smtp" section of appsettings.json or from
// Smtp__... environment variables. Until a mail server is configured,
// emails are written to the outbox folder as .eml files instead of sent,
// so the feature is visible without an email account. Controllers only
// enqueue; EmailDispatcher delivers on a background thread, so a slow or
// failing mail server can never delay or undo a request.
builder.Services.Configure<SmtpSettings>(builder.Configuration.GetSection("Smtp"));
builder.Services.AddSingleton<EmailQueue>();
builder.Services.AddHostedService<EmailDispatcher>();

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// The website is served from this same application, so CORS is not required.
// It is enabled anyway for localhost, in case the frontend is opened separately.
builder.Services.AddCors(o => o.AddPolicy("frontend", p =>
    p.SetIsOriginAllowed(origin =>
        Uri.TryCreate(origin, UriKind.Absolute, out var uri) &&
        (uri.Host == "localhost" || uri.Host == "127.0.0.1"))
     .AllowAnyHeader()
     .AllowAnyMethod()));

var app = builder.Build();

// ---------- Create, upgrade and seed the database ----------
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    var logger = scope.ServiceProvider.GetRequiredService<ILoggerFactory>()
                      .CreateLogger("Startup");

    // Creates the schema on a fresh install and adds anything missing to an
    // existing database, without touching the data already in it.
    DatabaseBootstrapper.EnsureUpToDate(db, logger);

    // Demo users, jobs and the published demo password are only for local
    // development. Production gets categories plus an optional administrator
    // whose credentials are supplied through secure environment variables.
    var seedDemoData = app.Environment.IsDevelopment() &&
                       builder.Configuration.GetValue("DailyWork:SeedDemoData", true);
    DbSeeder.Seed(
        db,
        includeDemoAccounts: seedDemoData,
        adminName: builder.Configuration["DAILYWORK_ADMIN_NAME"],
        adminEmail: builder.Configuration["DAILYWORK_ADMIN_EMAIL"],
        adminPhone: builder.Configuration["DAILYWORK_ADMIN_PHONE"],
        adminPassword: builder.Configuration["DAILYWORK_ADMIN_PASSWORD"]);

    if (!seedDemoData && !db.Users.Any())
    {
        throw new InvalidOperationException(
            "The production database has no administrator. Set DAILYWORK_ADMIN_EMAIL and DAILYWORK_ADMIN_PASSWORD (at least 12 characters) before first startup.");
    }
}

// ---------- Error handling ----------
// Unhandled faults return a generic message. The detail goes to the server log,
// never to the browser, so an error cannot leak table names or file paths.
app.UseExceptionHandler(branch => branch.Run(async context =>
{
    var feature = context.Features.Get<IExceptionHandlerFeature>();
    var logger = context.RequestServices.GetRequiredService<ILoggerFactory>()
                        .CreateLogger("UnhandledException");

    logger.LogError(feature?.Error, "Unhandled error on {Path}", context.Request.Path);

    context.Response.StatusCode = StatusCodes.Status500InternalServerError;
    context.Response.ContentType = "application/json";
    await context.Response.WriteAsync(
        "{\"message\":\"Something went wrong. Please try again.\"}");
}));

app.UseSwagger();
app.UseSwaggerUI();

// Serve the website that lives in wwwroot (index.html at the site root).
app.UseDefaultFiles();
app.UseStaticFiles();

app.UseCors("frontend");
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();

Console.WriteLine();
Console.WriteLine("====================================================");
Console.WriteLine("  DailyWork is running");
Console.WriteLine();
var baseUrl = app.Urls.FirstOrDefault()?.TrimEnd('/') ?? $"http://localhost:{port}";
Console.WriteLine("  Website:  " + baseUrl);
Console.WriteLine("  API docs: " + baseUrl + "/swagger");
var emailQueue = app.Services.GetRequiredService<EmailQueue>();
Console.WriteLine("  Email:     " + emailQueue.Describe());
Console.WriteLine();
Console.WriteLine("  Keep this window open. Press Ctrl+C to stop.");
Console.WriteLine("====================================================");
Console.WriteLine();

app.Run();
