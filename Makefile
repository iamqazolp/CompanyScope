.PHONY: ingest index seed-cloud api web ui lint typecheck test eval pricing

ingest:
	python -m src.ingest

index:
	python -m src.embed

seed-cloud:
	python -m scripts.seed_cloud

pricing:
	python -m scripts.manage_model_pricing

api:
	uvicorn src.app:app --reload --port 8000

web:
	npm run dev

ui:
	streamlit run streamlit_app.py

lint:
	ruff check src/ scripts/ api/ tests/

typecheck:
	mypy src/ api/ --ignore-missing-imports
	npm run typecheck

test:
	pytest tests/test_cloud_web.py tests/test_data_sources.py -v

eval:
	pytest tests/test_eval.py -v --json-report --json-report-file=report.json
	python scripts/check_thresholds.py report.json
