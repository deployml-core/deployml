# 🎯 Grafana Dashboard Queries - Copy & Paste Ready

## Dashboard: ML Model Monitoring

### Panel 1: Total Predictions (Stat Panel)

**Visualization**: Stat  
**Query**:
```sql
SELECT COUNT(*) as value FROM prediction_logs;
```

**Panel Settings**:
- Title: "Total Predictions"
- Unit: Short
- Color mode: Value

---

### Panel 2: Predictions Over Time (Time Series)

**Visualization**: Time series  
**Query**:
```sql
SELECT
  DATE_TRUNC('minute', timestamp) as time,
  COUNT(*) as "Predictions"
FROM prediction_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY time
ORDER BY time;
```

**Panel Settings**:
- Title: "Predictions Per Minute"
- X-axis: Time
- Y-axis: Count

---

### Panel 3: Average Price Prediction (Stat Panel)

**Visualization**: Stat  
**Query**:
```sql
SELECT ROUND(AVG(prediction), 2) as value 
FROM prediction_logs;
```

**Panel Settings**:
- Title: "Avg Prediction"
- Unit: Currency USD ($)
- Decimals: 0

---

### Panel 4: Price Distribution (Bar Chart)

**Visualization**: Bar chart  
**Query**:
```sql
SELECT
  CASE 
    WHEN prediction < 200000 THEN '< $200k'
    WHEN prediction < 300000 THEN '$200k-$300k'
    WHEN prediction < 400000 THEN '$300k-$400k'
    WHEN prediction < 500000 THEN '$400k-$500k'
    ELSE '> $500k'
  END as price_range,
  COUNT(*) as count
FROM prediction_logs
GROUP BY price_range
ORDER BY price_range;
```

**Panel Settings**:
- Title: "Price Distribution"
- X-axis: Price Range
- Y-axis: Count

---

### Panel 5: Feature Averages (Table)

**Visualization**: Table  
**Query**:
```sql
SELECT
  ROUND(AVG(CAST(features->>'bedrooms' AS FLOAT)), 2) as "Avg Bedrooms",
  ROUND(AVG(CAST(features->>'bathrooms' AS FLOAT)), 2) as "Avg Bathrooms",
  ROUND(AVG(CAST(features->>'sqft' AS FLOAT)), 0) as "Avg Sqft",
  ROUND(AVG(CAST(features->>'age' AS FLOAT)), 1) as "Avg Age"
FROM prediction_logs;
```

**Panel Settings**:
- Title: "Average Input Features"
- Table view

---

### Panel 6: Processing Time (Time Series)

**Visualization**: Time series  
**Query**:
```sql
SELECT
  timestamp as time,
  processing_time_ms as "Processing Time (ms)"
FROM prediction_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp;
```

**Panel Settings**:
- Title: "Processing Time"
- Unit: milliseconds (ms)
- Y-axis: Time

---

### Panel 7: Recent Predictions (Table)

**Visualization**: Table  
**Query**:
```sql
SELECT
  timestamp,
  CAST(features->>'bedrooms' AS INT) as bedrooms,
  CAST(features->>'bathrooms' AS INT) as bathrooms,
  CAST(features->>'sqft' AS INT) as sqft,
  CAST(features->>'age' AS INT) as age,
  ROUND(prediction::numeric, 0) as "price ($)"
FROM prediction_logs
ORDER BY timestamp DESC
LIMIT 10;
```

**Panel Settings**:
- Title: "Recent Predictions"
- Show as table

---

### Panel 8: Predictions by Bedrooms (Bar Gauge)

**Visualization**: Bar gauge  
**Query**:
```sql
SELECT
  CAST(features->>'bedrooms' AS TEXT) as bedroom_count,
  COUNT(*) as predictions,
  ROUND(AVG(prediction), 0) as avg_price
FROM prediction_logs
GROUP BY features->>'bedrooms'
ORDER BY bedroom_count;
```

**Panel Settings**:
- Title: "Predictions by Bedroom Count"
- Display mode: Basic
- Orientation: Horizontal

---

## 🎨 Dashboard Layout Suggestion

```
┌─────────────┬─────────────┬──────────────────────┐
│   Total     │  Avg Price  │  Predictions/Time    │
│ Predictions │             │                      │
├─────────────┴─────────────┴──────────────────────┤
│          Price Distribution (Bar Chart)          │
├──────────────────────────┬───────────────────────┤
│   Processing Time        │  Feature Averages     │
│   (Time Series)          │  (Table)              │
├──────────────────────────┴───────────────────────┤
│          Recent Predictions (Table)              │
├──────────────────────────────────────────────────┤
│   Predictions by Bedrooms (Bar Gauge)            │
└──────────────────────────────────────────────────┘
```

## 🚀 Quick Create Steps

1. Click **+ → Dashboard**
2. Click **Add visualization**
3. Select **Metrics Database** data source
4. Click **Code** to switch to SQL mode
5. Copy & paste one of the queries above
6. Set the visualization type (top right)
7. Click **Apply**
8. Repeat for each panel
9. Arrange panels by dragging
10. Click **💾 Save dashboard**

## 🎯 Pro Tips

- Use **Variables** for dynamic filtering (e.g., date ranges)
- Set **Auto-refresh** to 30s or 1m for live monitoring
- Add **Alerts** on key metrics (e.g., if processing time > 100ms)
- Create **multiple dashboards** for different views:
  - Real-time Monitoring
  - Historical Analysis
  - Model Performance
  - Feature Analysis

## 📝 Advanced Queries: Drift & Batch Results

### Panel 9: Drift Detection Summary (Stat)

**Visualization**: Stat  
**Query**:
```sql
SELECT COUNT(*) as value
FROM drift_metrics
WHERE drift_detected = true
  AND timestamp > NOW() - INTERVAL '7 days';
```

**Panel Settings**:
- Title: "Features with Drift (Last 7 Days)"
- Color: Red if > 0

---

### Panel 10: Drift Scores Over Time (Time Series)

**Visualization**: Time series  
**Query**:
```sql
SELECT
  timestamp as time,
  feature_name,
  drift_score as "PSI Score"
FROM drift_metrics
WHERE timestamp > NOW() - INTERVAL '30 days'
ORDER BY timestamp;
```

**Panel Settings**:
- Title: "Drift Scores by Feature"
- Legend: Show
- Thresholds: 0.1 (yellow), 0.2 (red)

---

### Panel 11: Latest Drift Metrics (Table)

**Visualization**: Table  
**Query**:
```sql
SELECT
  feature_name as "Feature",
  ROUND(drift_score::numeric, 4) as "PSI Score",
  ROUND(ks_statistic::numeric, 4) as "KS Statistic",
  ROUND(ks_pvalue::numeric, 4) as "KS P-Value",
  drift_detected as "Drift?",
  ROUND(reference_mean::numeric, 2) as "Ref Mean",
  ROUND(current_mean::numeric, 2) as "Current Mean",
  timestamp
FROM drift_metrics
WHERE timestamp = (SELECT MAX(timestamp) FROM drift_metrics)
ORDER BY drift_score DESC;
```

**Panel Settings**:
- Title: "Latest Drift Analysis"
- Conditional formatting: Red if drift_detected = true

---

### Panel 12: Batch Predictions Summary (Table)

**Visualization**: Table  
**Query**:
```sql
SELECT
  batch_id as "Batch ID",
  timestamp as "Run Time",
  total_records as "Records",
  ROUND(avg_prediction::numeric, 0) as "Avg Price ($)",
  ROUND(min_prediction::numeric, 0) as "Min Price ($)",
  ROUND(max_prediction::numeric, 0) as "Max Price ($)",
  ROUND(processing_time_seconds::numeric, 2) as "Time (s)"
FROM batch_predictions
ORDER BY timestamp DESC
LIMIT 10;
```

**Panel Settings**:
- Title: "Recent Batch Scoring Runs"

---

### Panel 13: Batch Predictions Trend (Time Series)

**Visualization**: Time series  
**Query**:
```sql
SELECT
  timestamp as time,
  avg_prediction as "Average Price",
  min_prediction as "Min Price",
  max_prediction as "Max Price"
FROM batch_predictions
WHERE timestamp > NOW() - INTERVAL '30 days'
ORDER BY timestamp;
```

**Panel Settings**:
- Title: "Batch Prediction Trends"
- Y-axis: Currency USD

---

### Panel 14: Drift Alert Status (Table)

**Visualization**: Table with conditional coloring  
**Query**:
```sql
SELECT
  feature_name as "Feature",
  CASE 
    WHEN drift_score < 0.1 THEN '✅ No Drift'
    WHEN drift_score < 0.2 THEN '⚠️ Minor Drift'
    ELSE '🚨 Significant Drift'
  END as "Status",
  ROUND(drift_score::numeric, 4) as "PSI",
  period_start as "Period Start",
  period_end as "Period End"
FROM drift_metrics
WHERE timestamp = (SELECT MAX(timestamp) FROM drift_metrics)
ORDER BY drift_score DESC;
```

**Panel Settings**:
- Title: "Drift Alert Dashboard"

---

## 🔍 Quick Test Queries

### Check Drift Data Exists
```sql
SELECT COUNT(*) as drift_records FROM drift_metrics;
```

### Check Batch Data Exists
```sql
SELECT COUNT(*) as batch_runs FROM batch_predictions;
```

### Latest Drift Summary
```sql
SELECT * FROM drift_metrics ORDER BY timestamp DESC LIMIT 5;
```

### Latest Batch Summary
```sql
SELECT * FROM batch_predictions ORDER BY timestamp DESC LIMIT 5;
```

---

## 📊 Complete Dashboard Layout

```
┌────────────┬────────────┬───────────────┬──────────────┐
│   Total    │  Avg Price │ Drift Alerts  │ Batch Runs   │
│ Predictions│            │               │              │
├────────────┴────────────┴───────────────┴──────────────┤
│          Predictions Over Time (Time Series)           │
├────────────────────────┬───────────────────────────────┤
│   Price Distribution   │   Processing Time             │
├────────────────────────┴───────────────────────────────┤
│          Drift Scores Over Time (Time Series)          │
├────────────────────────────────────────────────────────┤
│          Latest Drift Metrics (Table)                  │
├────────────────────────┬───────────────────────────────┤
│  Feature Averages      │   Drift Alert Status          │
├────────────────────────┴───────────────────────────────┤
│          Recent Predictions (Table)                    │
├────────────────────────────────────────────────────────┤
│          Batch Predictions Summary (Table)             │
├────────────────────────────────────────────────────────┤
│          Batch Predictions Trend (Time Series)         │
└────────────────────────────────────────────────────────┘
```

