# Design doc: Smart-Meter Revenue Protection

| | |
|---|---|
| **Author** | Stanley Igwe |
| **Status** | Core build complete on the full Low Carbon London dataset |
| **Last updated** | 2026-10-26 |

## 1. Problem and users
- **Users:** revenue-protection managers and inspection teams at a distribution company; feeder and commercial managers.
- **Questions they need answered:** Which meters should inspectors visit this week? Which feeders lose the most? How much revenue is at stake?
- **Current pain (scenario):** inspections go to whoever complained or was flagged last, most visits find nothing, and AMI and vending data sit in separate systems.

## 2. Requirements
| Type | Requirement |
|---|---|
| Functional | Weekly consumed-vs-bought gap, feeder losses, per-meter scores, ranked inspection list with revenue at risk. |
| Data quality | Every reading reconciles to the lake; honest meters report exactly their real use; nulls and duplicates counted. |
| Evaluation | Precision at k against planted cases; ground truth never reaches the features (lineage-tested). |
| Scale | 168M readings today (8.5 GB CSV). DuckDB handles it on a laptop in minutes; the Spark version is for the 100x case. |

## 3. Design
- **Layers:** raw CSV → Delta `readings` (date partitions, Z-ordered by meter) → simulation boundary (metered daily) → weekly facts and features → scores.
- **Key choices:** tampering is applied in SQL from a ground-truth table, so the real data is never rewritten. Detection compares the same season a year apart and normalises by the feeder's median change. Rules are severity-weighted and each fires for one theft pattern, so every flag is explainable.

## 4. Options considered
| Decision | Options | Chosen | Why |
|---|---|---|---|
| Storage | Parquet folders; Delta; Iceberg | Delta | ACID writes, OPTIMIZE/Z-ORDER for meter scans, read by DuckDB, Spark and delta-rs alike. |
| Partitioning | By meter; by month; by date | By date + Z-order by meter | Loads arrive by day; Z-order recovers meter locality without 5,561 tiny partitions. |
| Engine | Spark only; DuckDB only; both | DuckDB for the full run, Spark proven equal in CI | One laptop is enough at this size; Spark is the scale-out path, and the equality test keeps both honest. |
| Scoring | Supervised model; rules; Isolation Forest | Rules + Isolation Forest | Real theft labels are scarce and biased by past inspections; rules are explainable to inspectors. |
| Feeder confirmation | Use it; drop it | Measured, reverted | It cut precision from 54.5% to 37.7%: feeder noise is as large as one household. |

## 5. Risks and what I'd change at 10x scale
- Bypasses are the hardest case (2 of 42 in the top 167): at meter level they look like a real drop in use. Transformer-level metering or neighbour comparison is the fix.
- The theft is synthetic; real cases mix patterns and may adapt to detection. Inspection outcomes should feed back as labels.
- At 10x: incremental MERGE loads per day, the Spark job on a cluster, and per-feeder models.
