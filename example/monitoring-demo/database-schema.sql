-- ============================================================================
-- ML Monitoring Database Schema
-- Complete schema for prediction logging, drift, explainability & fairness
-- ============================================================================

-- ============================================================================
-- 1. PREDICTION LOGGING
-- ============================================================================

CREATE TABLE IF NOT EXISTS prediction_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) UNIQUE,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    features JSONB,
    prediction FLOAT,
    latency_ms INTEGER
);

COMMENT ON TABLE prediction_logs IS 'Logs every prediction made by the model serving API';

-- ============================================================================
-- 2. EXPLAINABILITY METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS explainability_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100),
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    shap_bedrooms FLOAT,
    shap_bathrooms FLOAT,
    shap_sqft FLOAT,
    shap_age FLOAT,
    base_value FLOAT,
    prediction_value FLOAT,
    FOREIGN KEY (request_id) REFERENCES prediction_logs(request_id) ON DELETE CASCADE
);

COMMENT ON TABLE explainability_logs IS 'SHAP values for each prediction';

CREATE TABLE IF NOT EXISTS feature_importance_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    feature_name VARCHAR(100),
    importance_score FLOAT,
    rank INTEGER,
    calculation_method VARCHAR(50)
);

COMMENT ON TABLE feature_importance_log IS 'Aggregated feature importance over time';

-- ============================================================================
-- 3. FAIRNESS MONITORING
-- ============================================================================

CREATE TABLE IF NOT EXISTS fairness_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    metric_name VARCHAR(100),
    group_attribute VARCHAR(50),
    group_value VARCHAR(50),
    metric_value FLOAT,
    threshold_violated BOOLEAN,
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    sample_size INTEGER
);

COMMENT ON TABLE fairness_metrics IS 'Fairness metrics across demographic groups';

-- ============================================================================
-- 4. DRIFT MONITORING
-- ============================================================================

CREATE TABLE IF NOT EXISTS drift_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    feature_name VARCHAR(100),
    drift_score FLOAT,
    ks_statistic FLOAT,
    ks_pvalue FLOAT,
    drift_detected BOOLEAN,
    model_version VARCHAR(50),
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    reference_mean FLOAT,
    current_mean FLOAT,
    reference_std FLOAT,
    current_std FLOAT
);

COMMENT ON TABLE drift_metrics IS 'Data drift detection results';

-- ============================================================================
-- 5. BATCH SCORING (Offline)
-- ============================================================================

CREATE TABLE IF NOT EXISTS batch_predictions (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(100) UNIQUE,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    total_records INTEGER,
    avg_prediction FLOAT,
    min_prediction FLOAT,
    max_prediction FLOAT,
    processing_time_seconds FLOAT
);

COMMENT ON TABLE batch_predictions IS 'Batch/offline scoring results';

-- ============================================================================
-- 6. MODEL PERFORMANCE METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    metric_name VARCHAR(100),
    metric_value FLOAT,
    dataset_name VARCHAR(100),
    sample_size INTEGER
);

COMMENT ON TABLE performance_metrics IS 'Model performance metrics over time';

-- ============================================================================
-- 7. ALERTS & NOTIFICATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS monitoring_alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    details JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100)
);

COMMENT ON TABLE monitoring_alerts IS 'Monitoring alerts and notifications';

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Prediction logs indexes
CREATE INDEX IF NOT EXISTS idx_pred_timestamp ON prediction_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_pred_timestamp_desc ON prediction_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pred_model_version ON prediction_logs(model_version);
CREATE INDEX IF NOT EXISTS idx_pred_request_id ON prediction_logs(request_id);

-- Explainability logs indexes
CREATE INDEX IF NOT EXISTS idx_exp_timestamp ON explainability_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exp_request_id ON explainability_logs(request_id);

-- Feature importance indexes
CREATE INDEX IF NOT EXISTS idx_feat_timestamp ON feature_importance_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_feat_feature_name ON feature_importance_log(feature_name);

-- Fairness metrics indexes
CREATE INDEX IF NOT EXISTS idx_fair_timestamp ON fairness_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_fair_metric_name ON fairness_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_fair_violated ON fairness_metrics(threshold_violated);
CREATE INDEX IF NOT EXISTS idx_fair_period ON fairness_metrics(period_start, period_end);

-- Drift metrics indexes
CREATE INDEX IF NOT EXISTS idx_drift_timestamp ON drift_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_drift_feature_name ON drift_metrics(feature_name);
CREATE INDEX IF NOT EXISTS idx_drift_detected ON drift_metrics(drift_detected);
CREATE INDEX IF NOT EXISTS idx_drift_period ON drift_metrics(period_start, period_end);

-- Batch predictions indexes
CREATE INDEX IF NOT EXISTS idx_batch_timestamp ON batch_predictions(timestamp);
CREATE INDEX IF NOT EXISTS idx_batch_id ON batch_predictions(batch_id);

-- Performance metrics indexes
CREATE INDEX IF NOT EXISTS idx_perf_timestamp ON performance_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_perf_metric_name ON performance_metrics(metric_name);

-- Monitoring alerts indexes
CREATE INDEX IF NOT EXISTS idx_alert_timestamp ON monitoring_alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON monitoring_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alert_acknowledged ON monitoring_alerts(acknowledged);

-- ============================================================================
-- USEFUL VIEWS
-- ============================================================================

-- Recent predictions with SHAP values
CREATE OR REPLACE VIEW recent_predictions_with_explainability AS
SELECT 
    p.request_id,
    p.timestamp,
    p.model_version,
    p.features,
    p.prediction,
    e.shap_bedrooms,
    e.shap_bathrooms,
    e.shap_sqft,
    e.shap_age,
    e.base_value
FROM prediction_logs p
LEFT JOIN explainability_logs e ON p.request_id = e.request_id
ORDER BY p.timestamp DESC;

-- Drift summary
CREATE OR REPLACE VIEW drift_summary AS
SELECT 
    feature_name,
    COUNT(*) as total_checks,
    SUM(CASE WHEN drift_detected THEN 1 ELSE 0 END) as drift_count,
    AVG(drift_score) as avg_drift_score,
    MAX(timestamp) as last_checked
FROM drift_metrics
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY feature_name;

-- Fairness violations
CREATE OR REPLACE VIEW fairness_violations AS
SELECT 
    timestamp,
    metric_name,
    group_attribute,
    group_value,
    metric_value,
    sample_size
FROM fairness_metrics
WHERE threshold_violated = TRUE
ORDER BY timestamp DESC;

-- ============================================================================
-- PERMISSIONS (Optional - adjust based on your setup)
-- ============================================================================

-- Grant permissions to monitoring user
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO monitoring_user;
-- GRANT SELECT ON ALL VIEWS IN SCHEMA public TO grafana_user;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check if tables are created
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN (
    'prediction_logs', 
    'explainability_logs', 
    'drift_metrics', 
    'fairness_metrics',
    'feature_importance_log',
    'batch_predictions',
    'performance_metrics',
    'monitoring_alerts'
  )
ORDER BY table_name;

-- Count records in each table
SELECT 
    'prediction_logs' as table_name, COUNT(*) as count FROM prediction_logs
UNION ALL
SELECT 'explainability_logs', COUNT(*) FROM explainability_logs
UNION ALL
SELECT 'drift_metrics', COUNT(*) FROM drift_metrics
UNION ALL
SELECT 'fairness_metrics', COUNT(*) FROM fairness_metrics
UNION ALL
SELECT 'feature_importance_log', COUNT(*) FROM feature_importance_log
UNION ALL
SELECT 'batch_predictions', COUNT(*) FROM batch_predictions
UNION ALL
SELECT 'performance_metrics', COUNT(*) FROM performance_metrics
UNION ALL
SELECT 'monitoring_alerts', COUNT(*) FROM monitoring_alerts;
