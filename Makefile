.PHONY: ingest index api ui lint typecheck test eval

ingest:
	python -m src.ingest

index:
	python -m src.embed

api:
	uvicorn src.app:app --reload --port 8000

ui:
	streamlit run streamlit_app.py

lint:
	ruff check .

typecheck:
	mypy src/ --ignore-missing-imports

eval:
	pytest tests/test_eval.py -v --json-report --json-report-file=report.json
	python scripts/check_thresholds.py report.json
