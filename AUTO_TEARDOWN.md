# Auto-Teardown Demo

This demo shows how to test the auto-teardown feature with a 10-minute duration.

## Quick Start

### 1. Update Configuration

Edit `teardown-demo.yaml` and update:
- `project_id`: Your GCP project ID
- `region`: Your preferred GCP region

### 2. Deploy with Auto-Teardown

```bash
deployml deploy --config-path demo/teardown-demo.yaml
```

You should see output like:
```
✅ Deployment complete!

⏰ Auto-teardown scheduled for: 2025-01-15 14:10:00 UTC
   (in 24 hours)
   To cancel: deployml teardown cancel --config-path demo/teardown-demo.yaml
```

### 3. Check Teardown Status

```bash
deployml teardown status --config-path demo/teardown-demo.yaml
```

### 4. Monitor Teardown

**Watch the countdown:**
```bash
watch -n 60 "deployml teardown status --config-path demo/teardown-demo.yaml"
```

**Check Cloud Scheduler:**
```bash
gcloud scheduler jobs describe deployml-teardown-teardown-demo-stack \
  --location us-west1 \
  --project YOUR_PROJECT_ID
```

**Check Cloud Function logs:**
```bash
gcloud functions logs read deployml-teardown-teardown-demo-stack \
  --region us-west1 \
  --project YOUR_PROJECT_ID \
  --limit 50
```

### 5. Verify Teardown Executed

After 10 minutes, check:

```bash
# Check if infrastructure still exists
gcloud run services list --project YOUR_PROJECT_ID

# Check Cloud Function logs for teardown execution
gcloud functions logs read deployml-teardown-teardown-demo-stack \
  --region us-west1 \
  --project YOUR_PROJECT_ID \
  --limit 10
```

### 6. Cancel Teardown (Optional)

If you want to cancel before the scheduled time:

```bash
deployml teardown cancel --config-path demo/teardown-demo.yaml
```

## What Happens

1. **Deployment**: Infrastructure is deployed normally
2. **Scheduler Created**: Cloud Scheduler job is created to trigger teardown in 10 minutes
3. **Wait**: Wait 10 minutes
4. **Teardown**: Cloud Scheduler triggers Cloud Function
5. **Destroy**: Cloud Function runs `terraform destroy`
6. **Cleanup**: All infrastructure resources are destroyed

## Configuration Details

- **duration_hours**: `0.167` = 10 minutes (10/60 hours)
- **time_zone**: `UTC` (you can change this)
- **enabled**: `true` to enable auto-teardown

## Troubleshooting

### Teardown didn't execute

1. Check Cloud Scheduler job status:
   ```bash
   gcloud scheduler jobs describe deployml-teardown-teardown-demo-stack \
     --location us-west1 \
     --project YOUR_PROJECT_ID
   ```

2. Check Cloud Function logs:
   ```bash
   gcloud functions logs read deployml-teardown-teardown-demo-stack \
     --region us-west1 \
     --project YOUR_PROJECT_ID
   ```

3. Manually trigger the function (for testing):
   ```bash
   # Get the function URL
   FUNCTION_URL=$(gcloud functions describe deployml-teardown-teardown-demo-stack \
     --region us-west1 \
     --project YOUR_PROJECT_ID \
     --format="value(httpsTrigger.url)")
   
   # Trigger it manually
   curl -X POST $FUNCTION_URL \
     -H "Content-Type: application/json" \
     -d '{
       "workspace_name": "teardown-demo-stack",
       "project_id": "YOUR_PROJECT_ID"
     }'
   ```

## Cleanup After Demo

After the demo, clean up any remaining resources:

```bash
# If teardown didn't execute automatically
deployml destroy --config-path demo/teardown-demo.yaml

# Clean up the scheduler job if it still exists
gcloud scheduler jobs delete deployml-teardown-teardown-demo-stack \
  --location us-west1 \
  --project YOUR_PROJECT_ID \
  --quiet
```

