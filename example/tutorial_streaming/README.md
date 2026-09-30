# Delayed Ground Truth Tutorial (POC)

A small variant of the [end-to-end example](../README.md) that simulates new
incoming data arriving over time, with ground truth showing up after a delay
instead of all at once. Built for issue #65.

**Assumption:** this expects a fresh `mlops` BigQuery dataset (no rows yet in
`offline_features`, `predictions`, `ground_truth`). If you already ran the
main `example/scripts/` walkthrough against the same deployment, either
`deployml destroy` + `deployml deploy` again, or point this at a separate
deployment.

## Prerequisites

Same as the [main example](../README.md#prerequisites): a deployed stack,
`.env` from `deployml get-urls`, and the same Python dependencies.

## Steps

Run from the project root (where `.env` lives).

**1. Load training data with a cutoff**

```bash
python example/tutorial_streaming/01_load_and_cutoff.py
```

Generates the same 500-row synthetic housing dataset as the main example, but
only loads the first 40% (200 rows) into `offline_features`. The remaining
300 rows are held back to be streamed in later.

**2. Train a model**

```bash
python example/scripts/02_train_model.py
```

Unchanged from the main example. Trains on whatever is in `offline_features`
— now just the 200-row cutoff instead of the full 500.

**3. Register the model**

```bash
python example/scripts/03_register_model.py
```

Unchanged from the main example.

**4. Simulate the incoming data stream**

```bash
python example/tutorial_streaming/04_simulate_stream.py
```

Regenerates the same 500 rows (same seed as step 1) and takes the 300 held
back. Splits them into 5 batches of ~60 rows. For each batch: scores it via
FastAPI `/predict` (logged to `predictions` automatically), waits 30 seconds,
then writes ground truth for that batch to `ground_truth`. Takes about 2.5
minutes total.

**5. Compute drift metrics**

```bash
python example/scripts/06_compute_drift_metrics.py
```

Unchanged from the main example.

**6. Set up the Grafana dashboard**

```bash
python example/scripts/07_setup_grafana.py
```

Unchanged from the main example. Open `GRAFANA_URL` to watch predictions and
MAE update batch by batch if you run step 4 again, or re-run step 5 between
batches.

## Known limitations / future work

- The 30-second delay is a real `time.sleep`, not a simulated one, so it's
  tied to wall-clock demo time. A follow-up will replace it with backdated
  `event_timestamp`s so a full time series is visible immediately.
- This is a POC run manually as scripts. A follow-up will promote it into a
  `deployml tutorial` CLI command, including support for uploading your own
  dataset instead of the built-in housing one.
