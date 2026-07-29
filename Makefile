.PHONY: install test lint eval eval-blocks

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

# Injection eval — needs no external data, runs anywhere (used in CI).
eval:
	python -m loglens.eval inject tests/data/HDFS_2k.log

# Block-level eval from a raw log (mines it, needs the full log for complete blocks):
#   make eval-blocks LOG=path/to/HDFS.log LABELS=path/to/anomaly_label.csv
eval-blocks:
	python -m loglens.eval blocks $(LOG) $(LABELS)

# Block-level eval from loghub's precomputed occurrence matrix (fast, recommended):
#   make eval-matrix MATRIX=data/HDFS_v1/preprocessed/Event_occurrence_matrix.csv
eval-matrix:
	python -m loglens.eval matrix $(MATRIX)
