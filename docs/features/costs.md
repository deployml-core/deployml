# Cost Estimates

deployml uses [Infracost](https://www.infracost.io) to answer two different
questions about money, with one command each:

| Command | Question | Where the usage numbers come from |
|---|---|---|
| `deployml estimate` | What *will* this cost? | A light/heavy assumption, since the stack does not exist yet |
| `deployml costs` | What *is* this costing me? | Cloud Monitoring — your real requests, bytes, and uptime |

Neither is a billing statement. Both price resources at list rates; for the amount
you were actually charged, check the GCP Billing Console.

## Setup

```bash
brew install infracost
infracost auth login
```

`deployml costs` additionally needs Application Default Credentials and read access
to metrics:

```bash
gcloud auth application-default login
```

Run `deployml doctor --project-id YOUR_PROJECT` to confirm infracost is installed and
authenticated and that you hold `roles/monitoring.viewer`.

## Fixed cost vs usage cost

This is the distinction that makes the numbers make sense, and both commands are
built around it.

- **Always-on** resources bill 24/7 for existing, whether or not anyone touches
  them. Cloud SQL is the one that matters here.
- **Usage-based** resources bill per request, per GB, per byte scanned. Cloud Run,
  BigQuery, and GCS all scale to zero.

Infracost assumes **zero usage** unless you tell it otherwise. That is why a naive
estimate reports $0 for every usage-based service and makes the stack look free
apart from the database. Both commands fix this, in different ways.

## Before deploying: `deployml estimate`

```bash
deployml estimate
deployml estimate --profile heavy
```

Renders the Terraform your config would produce, prices it against a usage profile,
and splits the result:

```
  ~$35 / month   ($34.55 fixed  +  ~$0.92 usage)  USD

  ALWAYS-ON  (billed 24/7 even if you never use the stack)
    $   34.55  Cloud SQL    MLflow's backend database

  USAGE-BASED  (scales with activity · profile: light)
    $    0.44  BigQuery     prediction & feature queries
    $    0.24  GCS Bucket   MLflow model artifacts
    $    0.24  Cloud Run    MLflow tracking server

  Biggest lever: Cloud SQL is 97% of your cost and runs 24/7.
  Switch MLflow to a SQLite backend to drop this to ~$0/month.
```

`light` is a student working through the coursework; `heavy` is a busy course
project at roughly 10-20x the traffic. Switching profiles moves only the usage line
— the always-on baseline does not budge. That is the lesson: how hard you use the
stack barely matters next to whether the database is running.

No cloud credentials needed, and nothing is deployed.

## While deployed: `deployml costs`

```bash
deployml costs
deployml costs --days 7
```

Once the stack exists we can stop guessing. This reads your real usage out of Cloud
Monitoring — requests per service, bytes stored, bytes scanned, database uptime —
and prices that instead:

```
  ACTUAL COST  ·  gcp-mlops-stack
  Measured from your real GCP usage over the last 7 days.

  Run-rate: ~$36 / month   ($34.55 always-on  +  ~$1.42 measured usage)  USD
  Charged so far: ~$8.40   (7.0 days since deploy, approximate)

  ALWAYS-ON  (billed 24/7 while the stack exists)
    $   34.55  Cloud SQL    MLflow's backend database  ·  up 100% of window

  USAGE-BASED  (measured over 7 days, scaled to a month)
    $    0.71  Cloud Run    MLflow tracking server  ·  30.0k req/mo, 240 ms median
    $    0.44  BigQuery     prediction & feature queries  ·  0.041 TB/mo scanned

  You are a LIGHT user — your real usage is 0.6x the 'light' profile.

  Biggest lever: Cloud SQL is 96% of your cost and runs 24/7.
  Tear the stack down when you are not using it:  deployml destroy
```

Every usage line carries the measurement behind it, so you can see *why* a number
is what it is. Once you have run this, `light` and `heavy` stop being assumptions
you are billed for and become a label on your actual behaviour.

Counters (requests, bytes scanned) are summed over the window and scaled to 30
days. Levels (bytes stored) are averaged over the window. Anything Monitoring does
not report is priced at $0 and listed under "About these numbers", together with
the places where a measurement is an approximation — a zero is always explained,
never silently assumed.

## Cost shown during deploy

`deployml deploy` runs the usage-aware estimate after `terraform plan` and shows the
total before the confirmation prompt:

```
 Deploy stack? Monthly cost: ~$35.47 USD [y/N]:
```

If infracost is missing or unauthenticated the estimate is skipped and the deploy
continues.

## Configuration

```yaml
cost_analysis:
  enabled: true             # set to false to skip the estimate during deploy (default: true)
  warning_threshold: 50.0   # warn if monthly cost exceeds this (default: 100.0)
```

## Typical costs (Cloud Run stack)

A standard MLflow + FastAPI + Grafana deployment runs around **$35/month**, and
roughly 97% of that is the Cloud SQL instance. The usage-based services add well
under a dollar at student traffic levels.

- Cloud SQL PostgreSQL: from ~$7/month for the smallest instance to $25+ for
  production sizes. Billed continuously.
- Cloud Run: scales to zero, so a few cents per month at light traffic; $10-30/month
  under sustained load.
- Google Cloud Storage: ~$0.020 per GB per month.
- BigQuery: ~$0.020 per GB per month storage, plus query cost per byte scanned.
- Cloud VMs: ~$25/month for medium instances.
- GKE: no management fee for one zonal cluster, but you pay for the VM instances and
  load balancers, and MLflow on GKE provisions a small PersistentDisk. This adds up
  quickly.

## Cost Optimization

Tips to keep costs low while you are learning:

- **Use SQLite instead of Cloud SQL** where you can. Set
  `backend_store_uri: sqlite` instead of `postgresql` to remove the Cloud SQL
  instance entirely — that is the single biggest saving available, since it deletes
  ~97% of the bill. The minikube and GKE MLflow paths already do this, with sqlite on
  a PersistentVolumeClaim.
- **Always run `deployml destroy`** when you are done. Cloud SQL bills continuously,
  used or not. `deployml costs` reports database uptime so you can see how much of
  the month you actually left it running.
- **Enable auto-teardown** so a forgotten deployment cannot bill all semester.
- **Prefer Cloud Run for variable workloads** to take advantage of scale-to-zero.
