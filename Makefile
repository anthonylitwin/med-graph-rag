.PHONY: help api ui seed train

help:
	@echo "Available targets: help api ui seed train"

api:
	python apps/api/app/main.py

ui:
	npm --prefix apps/ui/react-app run dev

seed:
	python pipelines/ingestion/seed_sample_graph.py

train:
	python pipelines/training/train_dummy.py
