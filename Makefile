# Task runner for the Urdu Document Q&A project. Run `make` to list targets.
#
# Works from PowerShell, Git Bash, Linux and macOS. On Windows, recipes run in
# Git's bash so the same POSIX commands work everywhere.
#
# `make help` is built from this file: a `##@ Name` line starts a group, and the
# `## text` after a target becomes its description.

ifeq ($(OS),Windows_NT)
  GIT_ROOT := $(patsubst %/bin/bash.exe,%,$(firstword $(wildcard \
                C:/PROGRA~1/Git/bin/bash.exe C:/PROGRA~2/Git/bin/bash.exe)))
  ifeq ($(GIT_ROOT),)
    $(error Git for Windows not found; install it or run make from WSL)
  endif
  SHELL := $(GIT_ROOT)/bin/bash.exe
  # make runs one-word commands without a shell, so Git's awk/touch/find must be on PATH too
  export PATH := $(GIT_ROOT)/usr/bin;$(PATH)
  PY := .venv/Scripts/python.exe
  PYTHON_BOOT ?= py -3.12
else
  PY := .venv/bin/python
  PYTHON_BOOT ?= python3
endif

.DEFAULT_GOAL := help
STAMP := .venv/.installed

HOST ?= 127.0.0.1
PORT ?= 8000
UI_PORT ?= 8501
WEB_PORT ?= 5173
API_URL ?= http://localhost:$(PORT)
# CPU-only torch is ~2 GB smaller; set TORCH_INDEX= (empty) for a CUDA build
TORCH_INDEX ?= https://download.pytorch.org/whl/cpu
ENGINES ?= tesseract
ARGS ?=
# headless: no first-run email prompt and no auto-opened browser tab
STREAMLIT := $(PY) -m streamlit run ui/streamlit_app.py --server.headless true --server.port $(UI_PORT)

# Every command target is .PHONY (declared per group below), so a file with the same
# name never stops it from running. The only real file targets are $(PY) and $(STAMP),
# which create the venv and install dependencies once instead of on every command.

##@ Setup
.PHONY: help setup install env doctor

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nVariables: PORT=%s UI_PORT=%s HOST=%s ENGINES=%s LABEL= PDF= PAGES= ARGS=\n' \
	  "$(PORT)" "$(UI_PORT)" "$(HOST)" "$(ENGINES)"

setup: install env ## Create the venv, install dependencies and create .env

install: $(STAMP) ## Create .venv (Python 3.12) and install dependencies

$(PY):
	$(PYTHON_BOOT) -m venv .venv

# Reinstalls only when a requirements file changes
$(STAMP): requirements.txt requirements-dev.txt | $(PY)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install torch $(if $(TORCH_INDEX),--index-url $(TORCH_INDEX))
	$(PY) -m pip install -r requirements-dev.txt
	@touch $@

env: ## Create .env from .env.example (never overwrites)
	@if [ -f .env ]; then echo ".env already exists; leaving it unchanged"; \
	else cp .env.example .env && echo "Created .env; set GEMINI_API_KEY in it"; fi

doctor: ## Check Python env, LLM API keys, Tesseract + Urdu and Docker
	@ok() { printf '  \033[32mok\033[0m    %s\n' "$$1"; }; \
	bad() { printf '  \033[31mmissing\033[0m %s\n' "$$1"; }; \
	envval() { grep -E "^$$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r"'; }; \
	if [ -f "$(STAMP)" ]; then ok "Python env ($$($(PY) --version 2>&1))"; \
	else bad "Python env: run 'make install'"; fi; \
	if [ -f .env ]; then ok ".env"; else bad ".env: run 'make env'"; fi; \
	keyset() { [ -n "$$(envval "$$1")" ] || [ -n "$$(printenv "$$1")" ]; }; \
	for role in primary backup; do \
	  if [ $$role = primary ]; then prov="$$(envval LLM_PROVIDER)"; prov="$${prov:-gemini}"; \
	  else prov="$$(envval LLM_BACKUP_PROVIDER)"; fi; \
	  [ -z "$$prov" ] && continue; \
	  key="$$(echo "$$prov" | tr a-z A-Z)_API_KEY"; \
	  if keyset "$$key"; then ok "$$key is set ($$role LLM: $$prov)"; \
	  else bad "$$key: needed for the $$role LLM ($$prov); set it in .env"; fi; \
	done; \
	tess="$$(envval TESSERACT_CMD)"; tess="$${tess:-tesseract}"; \
	langs="$$("$$tess" --list-langs 2>/dev/null | tr -d '\r')"; \
	if [ -z "$$langs" ]; then bad "Tesseract: install it or set TESSERACT_CMD in .env"; \
	elif printf '%s\n' "$$langs" | grep -qx urd; then ok "Tesseract with Urdu (urd)"; \
	else bad "Tesseract Urdu model: add urd.traineddata to tessdata"; fi; \
	if command -v docker >/dev/null 2>&1; then ok "Docker ($$(docker --version | cut -d, -f1))"; \
	else bad "Docker: only needed for 'make docker-up'"; fi

##@ Run
.PHONY: backend frontend web web-install web-build dev dev-streamlit

backend: $(STAMP) ## Run the FastAPI backend with auto-reload (http://localhost:PORT/docs)
	$(PY) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

frontend: $(STAMP) ## Run the Streamlit frontend against API_URL (http://localhost:UI_PORT)
	@echo "Frontend: http://localhost:$(UI_PORT)  (backend: $(API_URL))"
	API_URL=$(API_URL) $(STREAMLIT)

web/node_modules: web/package.json web/package-lock.json
	cd web && npm install
	@touch $@

web-install: web/node_modules ## Install the React UI's npm packages

web: web/node_modules ## Run the React UI dev server against API_URL (http://localhost:WEB_PORT)
	cd web && API_URL=$(API_URL) npx vite --port $(WEB_PORT)

web-build: web/node_modules ## Build the React UI into web/dist
	cd web && npm run build

dev: $(STAMP) web/node_modules ## Run backend and React UI together; Ctrl+C stops both
	@echo "Backend: http://localhost:$(PORT)/docs   UI: http://localhost:$(WEB_PORT)"
	@$(PY) -m uvicorn app.main:app --host $(HOST) --port $(PORT) & api_pid=$$!; 	trap 'kill $$api_pid 2>/dev/null' EXIT; 	cd web && API_URL=$(API_URL) npx vite --port $(WEB_PORT)

dev-streamlit: $(STAMP) ## Run backend and the old Streamlit UI together
	@echo "Backend: http://localhost:$(PORT)/docs   Frontend: http://localhost:$(UI_PORT)"
	@$(PY) -m uvicorn app.main:app --host $(HOST) --port $(PORT) & api_pid=$$!; 	trap 'kill $$api_pid 2>/dev/null' EXIT; 	API_URL=$(API_URL) $(STREAMLIT)

##@ Quality
.PHONY: test lint lint-check

test: $(STAMP) ## Run all test suites (pass pytest options with ARGS="-k api -x")
	$(PY) -m pytest $(ARGS)

lint: $(STAMP) ## Format the code and apply safe lint fixes (ruff)
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

lint-check: $(STAMP) ## Check formatting and lint without changing files (for CI)
	$(PY) -m ruff format --check .
	$(PY) -m ruff check .

##@ Evaluation (see README: one gate per phase)
.PHONY: eval-classify eval eval-retrieval ocr-render ocr-compare

eval-classify: $(STAMP) ## Phase 1 gate: page classifier report on eval/documents
	$(PY) -m eval.classify_report

eval: $(STAMP) ## Full test-set run: make eval LABEL=baseline [ARGS="--no-reranker"]
	$(if $(LABEL),,$(error LABEL is required, e.g. make eval LABEL=baseline))
	$(PY) -m eval.run_eval --label $(LABEL) $(ARGS)

eval-retrieval: $(STAMP) ## Retrieval-only run, no LLM cost: make eval-retrieval LABEL=bge-m3
	$(if $(LABEL),,$(error LABEL is required, e.g. make eval-retrieval LABEL=bge-m3))
	$(PY) -m eval.run_eval --label $(LABEL) --retrieval-only $(ARGS)

ocr-render: $(STAMP) ## Render pages for OCR references: make ocr-render PDF=eval/documents/x.pdf PAGES="2 5"
	$(if $(PDF),,$(error PDF is required, e.g. make ocr-render PDF=eval/documents/x.pdf PAGES="2 5"))
	$(if $(PAGES),,$(error PAGES is required, e.g. PAGES="2 5"))
	$(PY) -m eval.ocr_compare render "$(PDF)" $(PAGES)

ocr-compare: $(STAMP) ## Phase 3 gate: OCR error rate, e.g. ENGINES=tesseract,gemini,docai
	$(PY) -m eval.ocr_compare run --engines $(ENGINES)

##@ Docker
.PHONY: docker-build docker-up docker-down docker-logs

docker-build: ## Build the image (includes Tesseract with Urdu)
	docker compose build

docker-up: ## Start backend (:8000) and frontend (:8501) in the background
	docker compose up --build -d
	@echo "Backend: http://localhost:8000/docs   Frontend: http://localhost:8501"

docker-down: ## Stop the containers (data in ./storage is kept)
	docker compose down

docker-logs: ## Follow container logs
	docker compose logs -f

##@ Housekeeping
.PHONY: clean

clean: ## Remove Python, pytest and ruff caches (never touches storage/ or eval data)
	find . -path ./.venv -prune -o -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) \
	  -print -exec rm -rf {} +
