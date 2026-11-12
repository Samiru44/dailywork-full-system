using System.Security.Claims;
using System.Text;
using DailyWork.Api.Data;
using DailyWork.Api.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

// Always serve on port 5000 so the bundled website can find the API.
builder.WebHost.UseUrls("http://localhost:5000");

// ---------- Database ----------
// SQLite needs no installation. To move to SQL Server, add the
// Microsoft.EntityFrameworkCore.SqlServer package, swap UseSqlite for
// UseSqlServer below, and update the connection string in appsettings.json.
builder.Services.AddDbContext<AppDbContext>(opt =>
    opt.UseSqlite(builder.Configuration.GetConnectionString("Default")));

// ---------- Authentication ----------
// The signing key comes from the environment when one is set, so a real
// deployment keeps its secret out of source control. See TokenService.JwtKey.
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
    DbSeeder.Seed(db);
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
Console.WriteLine("  Website:  http://localhost:5000");
Console.WriteLine("  API docs: http://localhost:5000/swagger");
var emailQueue = app.Services.GetRequiredService<EmailQueue>();
Console.WriteLine("  Email:     " + emailQueue.Describe());
Console.WriteLine();
Console.WriteLine("  Keep this window open. Press Ctrl+C to stop.");
Console.WriteLine("====================================================");
Console.WriteLine();

app.Run();
