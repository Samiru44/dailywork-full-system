# Controller-by-controller parity checklist

The existing source contains 16 ASP.NET Core API controllers. Migration is not complete until every item is tested against actual backend behaviour.

| Original controller | Current migration status |
|---|---|
| AuthController | First-pass Flask API present. Rate-limiter and JWT compatibility need integration tests. |
| JobsController | First-pass search, detail, create, update, close; recommender/email side-effects missing. |
| ApplicationsController | First-pass statuses and work records; email/CV and edge-case parity missing. |
| PaymentsController | First-pass partial/complete payment and audit; live transaction testing missing. |
| AdminController | Not ported. |
| CategoriesController | Not ported. |
| ContactController | Not ported. |
| EmployerController | Not ported. |
| NotificationsController | Not ported. |
| OrganizationController | Not ported. |
| ProfileController | Not ported. |
| ProjectsController | Not ported. |
| RatingsController | Not ported. |
| RecommendationsController | Not ported. |
| ReportsController | Not ported. |
| StatsController | Not ported. |

## Acceptance test scenarios

- Create worker/employer/organization (never admin), login/logout, retry and lockout, role/security-stamp invalidation.
- Worker profile, certifications, CV upload/download/access control and email attachment at application time.
- Job search/filter/sort/pages; verified organizations; job owner edit/close; matching notifications.
- Worker applies; shortlist, reject, accept, complete; hire capacity; invalid transitions; concurrency.
- Worker-submitted work day pending; employer approval/rejection; approved records only counted; no duplicate day; record dates.
- Completion raises payment once; exact integer cents; part payments; two confirmations; dispute and audit; payment cannot be over-recorded or edited after money changes hands.
- Reports, CSV exports, email notifications, admin moderation, category management, messages, organization projects, ratings.
- Verify MySQL foreign keys, indexes, migration counts and CV digests, historical audit and reproducible backups/rollback.
- Check responsive Bootstrap layouts on small/mobile/desktop and keyboard/accessible forms; compare screens to React baseline.
