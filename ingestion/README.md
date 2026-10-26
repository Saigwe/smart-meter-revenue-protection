# Ingestion

| Script | Writes |
|---|---|
| `load_lcl.py` | Delta `data/lake/readings`: the real London readings, nulls dropped, duplicates collapsed, partitioned by `reading_date`, Z-ordered by `meter_id`. A load report goes to `data/lake/_load_report.json`. |
| `simulate.py` | SYNTHETIC Delta tables `sim_meters`, `sim_tamper` (ground truth), `sim_vends`, `sim_feeder_supply`, fixed seed. |

```bash
make download   # https://data.london.gov.uk/download/vqm0d/04feba67-f1a3-4563-98d0-f3071e3d56d1/Partitioned%20LCL%20Data.zip
python ingestion/load_lcl.py --csv "data/raw/Small LCL Data/*.csv" --lake data/lake
python ingestion/simulate.py --lake data/lake
```
