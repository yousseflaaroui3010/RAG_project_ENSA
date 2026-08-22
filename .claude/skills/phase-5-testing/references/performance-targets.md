# Performance targets

Numbers, not process. The phase-5 skill body decides when to run these.
`quality-metrics` owns how a target gets written; this file is the default set
when nobody has picked one.

Every target here is a starting point. A project with a real requirement beats
this file, and that requirement gets written down before building, not after
measuring.

## Frontend, measured on staging

Run Lighthouse in an incognito window against the staging URL, not localhost.
Your machine is faster than your users' machines.

| Metric | Target | Fails at |
|---|---|---|
| Performance score | 90 or better | Under 75 |
| Largest Contentful Paint | Under 2.5s | Over 4s |
| Interaction to Next Paint | Under 200ms | Over 500ms |
| Cumulative Layout Shift | Under 0.1 | Over 0.25 |
| First Contentful Paint | Under 1.8s | Over 3s |
| Accessibility score | 90 or better | Under 80 |
npx lighthouse <staging-url> --output html --output-path ./lighthouse-report.html
A Lighthouse run on one machine is one sample. Judge real users at the 75th
percentile, split between phone and desktop, from field data if you have it.

## Backend

| Metric | Target | Fails at |
|---|---|---|
| Read endpoint, p95 | Under 200ms | Over 500ms |
| Anything calling a model, p95 | Under 5s | Over 10s |
| Full user-facing flow, p95 | Under 10s | Over 20s |
| Error rate | Under 1% | Over 5% |

Keep failed-request timing separate from successful. A request that fails
instantly pulls the average down while the service falls over, which is how a
dashboard stays green through an outage.

## Load

Tool: k6 or Artillery.

A useful first scenario: 50 concurrent users, 10 minutes, 2 requests per minute
each. Watch three things. Memory that climbs and never comes back down is a
leak. An error rate that spikes and stays up means something did not recover.
Response times drifting upward through the run means a queue is filling.

Read `plan-for-failure` before load testing anything that talks to a database.
The interesting failure is not the one at peak, it is that the system does not
come back on its own when the load drops.

## The rule underneath all of these

A number with no window and no percentile is a wish. "Fast" is not a target.
"p95 under 200ms measured on staging over a 10 minute window" is a target,
because you can watch it fail.