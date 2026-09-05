# Variables
PYTHON      ?= python3
PIP         ?= pip3
DEP_MNGR    ?= uv
META_KAGGLE_DIR ?= ~/downloads/KW/meta-kaggle
META_KAGGLE_CODE_DIR ?= ~/Downloads/KW/meta-kaggle-code
STAGE_DIR ?= stage
KERNEL_LIMIT ?= 10000
NEO4J_COMPOSE ?= deploy/neo4j-compose.yml

# Kaggle knowledge graph build settings
COMP_STAGE_DIR ?= databases/staging_data
COMP_DB ?= databases/comp-kg
KERNELS_PER_COMPETITION ?= 50
ISSUNDB_CLI ?= bin/issundb-cli
ISSUNDB_MCP ?= bin/issundb-mcp
MAP_SIZE_GB ?= 12

# Kernel knowledge graph build settings
KERNEL_DB ?= databases/kernel-kg

# Hugging Face dataset release settings
HF_OUTPUT ?= databases/hf-dataset
HF_REPO_ID ?= habedi/kaggle-knowledge-graph
HF_SNAPSHOT ?=
HF_VERSION ?= $(HF_SNAPSHOT)

# Directories and files to clean
CACHE_DIRS  = .mypy_cache .pytest_cache .ruff_cache
COVERAGE    = .coverage htmlcov coverage.xml
DIST_DIRS   = dist junit
TMP_DIRS   = site

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show help messages for all available targets
	@grep -E '^[a-zA-Z_-]+:.*## .*$$' Makefile | \
	awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Setup and Installation
.PHONY: setup
setup: ## Install system dependencies and dependency manager
	sudo apt-get update
	sudo apt-get install -y python3-pip
	$(PIP) install --upgrade pip
	$(PIP) install $(DEP_MNGR)

.PHONY: install
install: ## Install Python dependencies
	$(DEP_MNGR) sync --all-extras # --upgrade

# Quality and Testing
.PHONY: test
test: ## Run tests
	$(DEP_MNGR) run pytest

.PHONY: lint
lint: ## Run linter checks
	$(DEP_MNGR) run ruff check --fix

.PHONY: format
format: ## Format code
	$(DEP_MNGR) run ruff format

.PHONY: typecheck
typecheck: ## Typecheck code
	$(DEP_MNGR) run mypy .

.PHONY: setup-hooks
setup-hooks: ## Install Git hooks (pre-commit and pre-push)
	$(DEP_MNGR) run pre-commit install --hook-type pre-commit
	$(DEP_MNGR) run pre-commit install --hook-type pre-push
	$(DEP_MNGR) run pre-commit install-hooks

.PHONY: test-hooks
test-hooks: ## Test Git hooks on all files
	$(DEP_MNGR) run pre-commit run --all-files

# Documentation
.PHONY: docs
docs: ## Build documentation
	$(DEP_MNGR) run mkdocs build

# Build and Publish
.PHONY: build
build: ## Build distributions
	$(DEP_MNGR) build

.PHONY: publish
publish: ## Publish to PyPI (requires PYPI_TOKEN)
	$(DEP_MNGR) config pypi-token.pypi $(PYPI_TOKEN)
	$(DEP_MNGR) publish --build

# Maintenance
.PHONY: clean
clean: ## Remove caches and build artifacts
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf $(CACHE_DIRS) $(COVERAGE) $(DIST_DIRS) $(TMP_DIRS)

# Knowledge graph pipeline
.PHONY: kg-inspect
kg-inspect: ## Inspect Meta Kaggle CSV schemas and row counts
	META_KAGGLE_DIR="$(META_KAGGLE_DIR)" .venv/bin/python scripts/inspect_metadata.py

.PHONY: kg-stage
kg-stage: ## Stage a top-voted-kernel subset as graph node/edge CSVs
	META_KAGGLE_DIR="$(META_KAGGLE_DIR)" STAGE_DIR="$(STAGE_DIR)" .venv/bin/python scripts/stage_kernel_subset.py --kernel-limit $(KERNEL_LIMIT)

.PHONY: kg-stage-with-message-text
kg-stage-with-message-text: ## Stage subset and include forum message text columns
	META_KAGGLE_DIR="$(META_KAGGLE_DIR)" STAGE_DIR="$(STAGE_DIR)" .venv/bin/python scripts/stage_kernel_subset.py --kernel-limit $(KERNEL_LIMIT) --include-message-text

.PHONY: kg-parse-imports
kg-parse-imports: ## Parse imports from Meta Kaggle Code for staged kernel versions
	META_KAGGLE_CODE_DIR="$(META_KAGGLE_CODE_DIR)" STAGE_DIR="$(STAGE_DIR)" .venv/bin/python scripts/parse_imports.py

.PHONY: kg-parse-api-calls
kg-parse-api-calls: ## Parse Python API calls from Meta Kaggle Code for staged kernel versions
	META_KAGGLE_CODE_DIR="$(META_KAGGLE_CODE_DIR)" STAGE_DIR="$(STAGE_DIR)" .venv/bin/python scripts/parse_api_calls.py

.PHONY: kg-stage-all
kg-stage-all: kg-stage kg-parse-imports kg-parse-api-calls ## Stage metadata, parsed import edges, and parsed API call edges

.PHONY: kg-load
kg-load: ## Load the staged kernel subset, add constraints and indexes, and validate
	STAGE_DIR="$(STAGE_DIR)" .venv/bin/python scripts/import_to_issundb.py --stage-dir "$(STAGE_DIR)" --db "$(KERNEL_DB)" --cli "$(ISSUNDB_CLI)" --map-size-gb $(MAP_SIZE_GB)

.PHONY: graph-kernel
graph-kernel: kg-inspect kg-stage-all kg-load ## Build the kernel knowledge graph end to end into $(KERNEL_DB)
	@echo "kernel-kg ready at $(KERNEL_DB)"

.PHONY: kernel-cli
kernel-cli: ## Open the kernel knowledge graph in the IssunDB CLI
	$(ISSUNDB_CLI) --map-size-gb $(MAP_SIZE_GB) $(KERNEL_DB)

.PHONY: kernel-mcp
kernel-mcp: ## Run the IssunDB MCP server for the kernel knowledge graph
	$(ISSUNDB_MCP) --db-path $(KERNEL_DB) --map-size-gb $(MAP_SIZE_GB)

# Kaggle knowledge graph
.PHONY: comp-stage
comp-stage: ## Stage the post-2020 competition subset (with forum message text)
	META_KAGGLE_DIR="$(META_KAGGLE_DIR)" .venv/bin/python scripts/stage_competition_subset.py --stage-dir "$(COMP_STAGE_DIR)" --kernels-per-competition $(KERNELS_PER_COMPETITION) --include-message-text

.PHONY: comp-parse-imports
comp-parse-imports: ## Parse library imports for the staged competition kernel versions
	META_KAGGLE_CODE_DIR="$(META_KAGGLE_CODE_DIR)" .venv/bin/python scripts/parse_imports.py --stage-dir "$(COMP_STAGE_DIR)"

.PHONY: comp-parse-api-calls
comp-parse-api-calls: ## Parse Python API calls for the staged competition kernel versions
	META_KAGGLE_CODE_DIR="$(META_KAGGLE_CODE_DIR)" .venv/bin/python scripts/parse_api_calls.py --stage-dir "$(COMP_STAGE_DIR)"

.PHONY: comp-load
comp-load: ## Load the staged competition subset, add constraints and indexes, and validate
	.venv/bin/python scripts/load_competition_kg.py --stage-dir "$(COMP_STAGE_DIR)" --db "$(COMP_DB)" --cli "$(ISSUNDB_CLI)" --map-size-gb $(MAP_SIZE_GB)

.PHONY: graph-kc
graph-kc: kg-inspect comp-stage comp-parse-imports comp-parse-api-calls comp-load ## Build the Kaggle knowledge graph end to end into $(COMP_DB)
	@echo "comp-kg ready at $(COMP_DB)"

.PHONY: comp-cli
comp-cli: ## Open the Kaggle knowledge graph in the IssunDB CLI
	$(ISSUNDB_CLI) --map-size-gb $(MAP_SIZE_GB) $(COMP_DB)

.PHONY: comp-mcp
comp-mcp: ## Run the IssunDB MCP server for the Kaggle knowledge graph
	$(ISSUNDB_MCP) --db-path $(COMP_DB) --map-size-gb $(MAP_SIZE_GB)

.PHONY: hf-package
hf-package: ## Package the staged competition graph as a Hugging Face dataset (needs HF_SNAPSHOT=YYYY-MM-DD)
	@test -n "$(HF_SNAPSHOT)" || (echo "set HF_SNAPSHOT to the Meta Kaggle export date, e.g. make hf-package HF_SNAPSHOT=2026-08-01" && exit 1)
	.venv/bin/python scripts/package_hf_dataset.py --stage-dir "$(COMP_STAGE_DIR)" --output "$(HF_OUTPUT)" --repo-id "$(HF_REPO_ID)" --snapshot "$(HF_SNAPSHOT)" --version "$(HF_VERSION)"

.PHONY: hf-upload
hf-upload: ## Upload the packaged dataset to the Hugging Face Hub (needs `hf auth login` and HF_VERSION)
	@test -n "$(HF_VERSION)" || (echo "set HF_VERSION (or HF_SNAPSHOT) to tag the release" && exit 1)
	hf upload "$(HF_REPO_ID)" "$(HF_OUTPUT)" . --repo-type dataset --commit-message "Release $(HF_VERSION)"
	hf repo tag create "$(HF_REPO_ID)" "$(HF_VERSION)" --repo-type dataset

.PHONY: neo4j-up
neo4j-up: ## Start Neo4j with stage/ mounted as /import
	docker compose -f $(NEO4J_COMPOSE) up -d

.PHONY: neo4j-down
neo4j-down: ## Stop Neo4j
	docker compose -f $(NEO4J_COMPOSE) down
