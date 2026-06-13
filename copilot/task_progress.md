# Phase 13A Sprint 2 — Phase 1 Implementation Todo

## Phase 1: Data Foundation Layer

### 1. Database Query Helpers
- [x] Create `copilot/helpers/__init__.py`
- [ ] Create `copilot/helpers/db_queries.py` — parameterised SQL query functions
- [ ] Create `copilot/helpers/tenant_filter.py` — `apply_tenant_filter()` utility
- [ ] Create `copilot/helpers/health_helper.py` — inline `_evaluate_health()` logic

### 2. Redis Cache Layer
- [ ] Create `copilot/cache/__init__.py` — cache abstraction
- [ ] Create `copilot/cache/redis_cache.py` — Redis-backed cache implementation

### 3. LLM Provider Abstraction
- [ ] Create `copilot/providers/__init__.py`
- [ ] Create `copilot/providers/base_provider.py` — abstract base
- [ ] Create `copilot/providers/openrouter_provider.py` — OpenRouter DeepSeek V3 (primary)
- [ ] Create `copilot/providers/ollama_local_provider.py` — Local Ollama qwen3:4b (secondary)
- [ ] Create `copilot/providers/ollama_cloud_provider.py` — Ollama Cloud (tertiary)
- [ ] Create `copilot/providers/two_tier_provider.py` — Three-tier fallback wrapper

### 4. Tests
- [ ] Create `copilot/tests/__init__.py`
- [ ] Create `copilot/tests/test_db_queries.py`
- [ ] Create `copilot/tests/test_tenant_filter.py`
- [ ] Create `copilot/tests/test_health_helper.py`
- [ ] Create `copilot/tests/test_cache.py`
- [ ] Create `copilot/tests/test_providers.py`

### 5. Reports
- [ ] Create `PHASE13A_SPRINT2_PHASE1_IMPLEMENTATION_REPORT.md`
- [ ] Create `PHASE13A_SPRINT2_PHASE1_VALIDATION_REPORT.md`