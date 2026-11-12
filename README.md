# DailyWork — Full System

**Job Matching and Payment Tracking System for Daily Wage Workers in Sri Lanka**

DailyWork is a full-stack web application built with ASP.NET Core 8, Entity Framework Core, SQLite, and a React-based single-page frontend served by the API.

## Project status

This repository is being prepared for source upload and deployment. The application source will be added from the reviewed project package.

## Technology

- ASP.NET Core 8 Web API (C#)
- React 18, HTML, CSS, JavaScript
- Entity Framework Core 8
- SQLite (current development database)
- JWT authentication and BCrypt password hashing
- SMTP email notification support (Brevo/Gmail for local development)

## Important security notes

- Keep this repository private while preparing the deployment.
- Never commit real SMTP passwords, API keys, JWT signing keys, production connection strings, environment files, or database files.
- Configure production secrets through the hosting provider environment-variable settings.
- The development seed data contains demonstration accounts. Do not use the documented demo credentials as production credentials.
- Before public deployment, configure a production database and verify the production seeding and administrator-account process.

## Local setup

After the source upload is complete, follow the instructions in HOW-TO-RUN.md from the repository root.
