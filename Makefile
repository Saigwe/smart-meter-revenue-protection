PY ?= python
CSV ?= data/raw/Small LCL Data/*.csv
LAKE ?= data/lake
DB ?= warehouse/meters.duckdb
RESULTS ?= results
DBT_BIN ?= dbt
LCL_ZIP = https://data.london.gov.uk/download/vqm0d/04feba67-f1a3-4563-98d0-f3071e3d56d1/Partitioned%20LCL%20Data.zip

.PHONY: all download load simulate dbt score test spark fixture-all clean

all: load simulate dbt score test   ## the real 167.9M readings (run `make download` once first)

download:   ## 759 MB zip from the London Datastore, 8.5 GB of CSVs once extracted
	mkdir -p data/raw
	curl -L -o "data/raw/Partitioned LCL Data.zip" "$(LCL_ZIP)"
	cd data/raw && unzip -q -o "Partitioned LCL Data.zip"

load:       ## CSV -> Delta, partitioned by date, Z-ordered by meter
	$(PY) ingestion/load_lcl.py --csv "$(CSV)" --lake $(LAKE)

simulate:   ## SYNTHETIC vends, feeders and planted theft
	$(PY) ingestion/simulate.py --lake $(LAKE)

dbt:
	cd dbt && DUCKDB_PATH=../$(DB) $(DBT_BIN) build --profiles-dir . --vars '{lake: "../$(LAKE)"}'

score:      ## rules + isolation forest, precision on the planted cases, inspection list
	$(PY) analysis/score_meters.py --db $(DB) --lake $(LAKE) --out $(RESULTS)

test:
	$(PY) -m pytest -q tests

spark:      ## the same pipeline as Spark jobs on the Delta lake (needs Java; runs in CI)
	$(PY) spark/meter_jobs.py --lake $(LAKE) --out $(RESULTS)/spark_timings.json

fixture-all:   ## synthetic LCL-format CSVs through the same pipeline (CI)
	$(PY) tests/fixtures/make_fixture.py --out data/fixture/raw
	$(MAKE) all CSV="data/fixture/raw/*.csv" LAKE=data/fixture/lake DB=warehouse/fixture.duckdb RESULTS=data/fixture/results

clean:
	rm -rf warehouse dbt/target dbt/logs data/lake data/fixture
