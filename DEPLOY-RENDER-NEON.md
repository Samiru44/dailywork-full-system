# DailyWork deployment (Render + Neon + Brevo)

This repository includes a .NET 10 LTS Dockerfile for a Render Web Service, PostgreSQL support through Neon, and Brevo transactional email through HTTPS. Keep the GitHub repository private while configuring deployment.

## Runtime support

The deployment branch targets .NET 10 LTS. .NET 8 reached end of support on November 10, 2026, so the hosted build uses the supported .NET 10 runtime.

## Important free-tier limitations

- Render Free web services sleep after 15 minutes without requests and can take around a minute to wake up. Their filesystem is ephemeral, so do not store the production database or important uploads on the web service.
- Neon Free currently includes 1 GB per project and 100 compute-hours per project per month; compute scales down after inactivity. Check the provider dashboard for current quota details.
- Brevo Free currently includes 300 email sends per day. A verified sender is required.
- These free tiers are suitable for a demonstration or coursework project, not a production service with uptime or data-retention guarantees.

## 1. Create a Neon PostgreSQL database

1. Create a project at https://neon.com/.
2. Copy the ADO.NET/Npgsql connection string. It must use Npgsql key/value format, for example:

   `Host=YOUR_NEON_HOST;Port=5432;Database=YOUR_DATABASE;Username=YOUR_USERNAME;Password=YOUR_PASSWORD;SSL Mode=Require;`

3. Do not put the connection string in GitHub. Add it only as the Render environment variable `ConnectionStrings__Default`.

## 2. Create the Render web service

1. Create a Render account at https://render.com/.
2. Choose **New → Web Service** and connect `Samiru44/dailywork-full-system`.
3. Select branch `deployment-prep` (or `main` after the deployment-prep changes have been merged).
4. Choose **Docker** as the runtime and leave the Dockerfile path as `./Dockerfile`.
5. Choose the Free plan for a demo. Render supplies the `PORT` variable; the app binds to `0.0.0.0` on that port.

Set these environment variables in Render (do not commit them):

| Variable | Value |
|---|---|
| `ASPNETCORE_ENVIRONMENT` | `Production` |
| `Database__Provider` | `PostgreSQL` |
| `ConnectionStrings__Default` | Your Neon Npgsql connection string |
| `DAILYWORK_ADMIN_NAME` | Your administrator display name |
| `DAILYWORK_ADMIN_EMAIL` | Your administrator email |
| `DAILYWORK_ADMIN_PHONE` | Your phone number (optional) |
| `DAILYWORK_ADMIN_PASSWORD` | A unique password of at least 12 characters |
| `DAILYWORK_JWT_KEY` | A random secret of at least 32 characters |
| `Smtp__Provider` | `BrevoApi` |
| `Smtp__ApiKey` | Your Brevo API key |
| `Smtp__From` | Your verified Brevo sender email |
| `Smtp__FromName` | `DailyWork` |
| `Smtp__SiteUrl` | Your `https://...onrender.com` service URL |

Create the database and set the administrator variables before the first deployment. The application defaults to PostgreSQL in Production, creates the initial schema, and creates the administrator only when the database has no users. It does not seed demo users or the published demo password outside Development.

## 3. Brevo sender and API key

1. Create or sign in to Brevo at https://www.brevo.com/.
2. Verify the sender email address in Brevo.
3. Create an API key and store it as `Smtp__ApiKey` in Render. Never commit or paste the key into source files.
4. The application sends transactional email using `POST https://api.brevo.com/v3/smtp/email` over HTTPS, not SMTP.

## 4. After the first deploy

- Open the Render service URL and `/swagger`.
- Test admin sign-in, registration, password reset, application notifications and email delivery.
- Confirm emails arrive at a real inbox; seeded `@dailywork.lk` demonstration addresses are intentionally not sent.
- Make a backup/export of the Neon database before major changes.

## Database schema updates

The legacy in-place bootstrapper is SQLite-specific. For a new PostgreSQL database this deployment branch uses `EnsureCreated()` to create the initial schema from the EF Core model. `EnsureCreated()` does not update existing tables. Before shipping future model changes, create and apply EF Core migrations for PostgreSQL; do not expect the SQLite bootstrapper to migrate a PostgreSQL database.
