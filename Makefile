.PHONY: help install build build-lambda test deploy clean lint format test-lambda test-quick

PYTHON := python3
PIP := pip3

help:
	@echo "BiospexReconcile - Lambda Build Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install           - Install Python dependencies"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build             - Build and deploy with deploy.sh"
	@echo "  make build-lambda      - Build and deploy with deploy.sh"
	@echo "  make deploy            - Deploy with deploy.sh"
	@echo ""
	@echo "Testing:"
	@echo "  make test              - Run local tests"
	@echo "  make test-lambda       - Test Lambda handler with mocked S3/SQS"
	@echo "  make test-quick        - Quick import/sample-file checks"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean             - Clean build artifacts"
	@echo "  make lint              - Lint Python code"
	@echo "  make format            - Format Python code"

install:
	$(PIP) install -r requirements.txt

build: build-lambda

build-lambda:
	@echo "[Deploy] Building and deploying with deploy.sh..."
	./deploy.sh

deploy: build-lambda

test:
	@echo "[Test] Running local tests..."
	$(PYTHON) test_local.py

test-lambda:
	@echo "[Test] Running Lambda handler tests with mocks..."
	$(PYTHON) test_lambda_mock.py

test-quick:
	@echo "[Test] Quick test with sample CSV..."
	$(PYTHON) -c "from lib import util; print('✓ Lib imports work')"
	@test -f test_sample.csv && echo "✓ Sample CSV exists"

lint:
	@echo "[Lint] Checking Python code..."
	$(PYTHON) -m pylint lambda_function.py lib/ --fail-under=7.0 --exit-zero || true

format:
	@echo "[Format] Formatting Python code..."
	$(PYTHON) -m black lambda_function.py lib/ test_*.py --line-length 120

clean:
	@echo "[Clean] Removing build artifacts..."
	rm -rf .build_lambda/ build/ *.zip __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✓ Clean complete"

.DEFAULT_GOAL := help
