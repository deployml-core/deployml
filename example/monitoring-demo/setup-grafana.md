# 📊 Grafana Setup Guide

## Connection Details

**Database**: PostgreSQL (Cloud SQL)  
**Host**: `34.83.142.98:5432`  
**Database Name**: `metrics`  
**Username**: `mlflow`  
**Password**: `Xv*xlwALsCAX*.jT`  
**SSL Mode**: `disable`

## Step 1: Add Data Source

1. Go to: **Configuration → Data Sources → Add data source**
2. Select **PostgreSQL**
3. Fill in the connection details above
4. **Important**: Use the public IP address (34.83.142.98:5432) for Host
5. Click "Save & Test"

## Step 2: Verify Data

Run this query in Grafana's Explore tab:

```sql
SELECT COUNT(*) FROM prediction_logs;
```

You should see: **100** (from the traffic we generated)

## Step 3: Sample Visualizations

### Panel 1: Predictions Over Time

```sql
SELECT
  DATE_TRUNC('minute', timestamp) as time,
  COUNT(*) as "Predictions",
  AVG(prediction) as "Avg Price"
FROM prediction_logs
WHERE $__timeFilter(timestamp)
GROUP BY time
ORDER BY time
```

**Visualization**: Time series  
**Y-axis**: Count and Average

### Panel 2: Prediction Distribution

```sql
SELECT
  ROUND(prediction / 100000) * 100000 as price_bucket,
  COUNT(*) as count
FROM prediction_logs
GROUP BY price_bucket
ORDER BY price_bucket
```

**Visualization**: Bar chart  
**X-axis**: Price bucket  
**Y-axis**: Count

### Panel 3: Feature Statistics

```sql
SELECT
  'bedrooms' as feature,
  AVG(CAST(features->>'bedrooms' AS FLOAT)) as avg_value
FROM prediction_logs
UNION ALL
SELECT
  'bathrooms' as feature,
  AVG(CAST(features->>'bathrooms' AS FLOAT)) as avg_value
FROM prediction_logs
UNION ALL
SELECT
  'sqft' as feature,
  AVG(CAST(features->>'sqft' AS FLOAT)) as avg_value
FROM prediction_logs
UNION ALL
SELECT
  'age' as feature,
  AVG(CAST(features->>'age' AS FLOAT)) as avg_value
FROM prediction_logs
```

**Visualization**: Table or Bar gauge

### Panel 4: Recent Predictions

```sql
SELECT
  timestamp,
  features->>'bedrooms' as bedrooms,
  features->>'bathrooms' as bathrooms,
  features->>'sqft' as sqft,
  features->>'age' as age,
  ROUND(prediction::numeric, 2) as prediction
FROM prediction_logs
ORDER BY timestamp DESC
LIMIT 10
```

**Visualization**: Table

### Panel 5: Processing Time

```sql
SELECT
  timestamp as time,
  processing_time_ms as "Processing Time (ms)"
FROM prediction_logs
WHERE $__timeFilter(timestamp)
ORDER BY timestamp
```

**Visualization**: Time series

## Step 4: Create Dashboard

1. Click **+ → Dashboard**
2. Add panels using the queries above
3. Arrange and save your dashboard
4. Name it: "ML Model Monitoring"

## Quick Test

After setting up the data source, go to **Explore** and run:

```sql
SELECT * FROM prediction_logs LIMIT 5;
```

You should see the 100 predictions we generated earlier!

## Troubleshooting

### "Database connection error"
- **Use the public IP address** (34.83.142.98:5432), not the Unix socket path
- The Unix socket path (`/cloudsql/...`) only works for services running in Cloud Run, not for UI connections
- Verify the password is exact (no extra spaces): `Xv*xlwALsCAX*.jT`
- Make sure Host is: `34.83.142.98:5432` (with port number)

### "Table doesn't exist"
- The FastAPI service might not have created the table yet
- Try making a prediction first to initialize the database
- Check FastAPI logs for database connection errors

### "No data"
- Verify predictions were logged: check `/stats` endpoint
- Make sure the time range in Grafana includes your test traffic time
- Check that the query syntax is correct for PostgreSQL

## Next Steps

Once monitoring is working:
- Set up alerts for drift detection
- Add prediction quality metrics
- Create custom dashboards for your specific needs
- Configure Grafana notifications (email, Slack, etc.)

