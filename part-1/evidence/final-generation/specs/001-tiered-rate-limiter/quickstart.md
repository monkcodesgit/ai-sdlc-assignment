# Quickstart & Validation: Tiered Rate Limiter

Run from `part-1/`.

## 1. Environment (Python 3.11+, see research R-001)

```bash
rm -rf .venv && /opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python --version   # expect 3.11.x or newer
```

## 2. Quality gates (Constitution Principle III)

```bash
.venv/bin/pytest --cov=ratelimiter --cov-report=term-missing --cov-fail-under=90
.venv/bin/ruff check --config .harness/ruff.toml src     # when .harness/ exists (R-007)
.venv/bin/bandit -r src -ll                              # zero MEDIUM/HIGH
grep -rnE "noqa|nosec|type: ?ignore" src && echo "FAIL: suppression found" || echo "OK"
```

Expected: all tests pass (AC-001–AC-031, NFR-004, NFR-005), coverage ≥ 90%, no findings.
Full harness (once present): `.venv/bin/python .harness/run_harness.py`.

## 3. Run the service

```bash
.venv/bin/uvicorn ratelimiter.main:app --app-dir src --host 127.0.0.1 --port 8000
```

## 4. Manual smoke scenarios ([contract](contracts/http-api.md))

```bash
curl -s localhost:8000/health                                   # {"status":"ok"}
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code} " -X POST localhost:8000/v1/check \
    -H 'content-type: application/json' -d '{"client_id":"alice","tier":"free"}'
done; echo                                                      # 200 200 200 200 200 429
curl -si -X POST localhost:8000/v1/check -H 'content-type: application/json' \
  -d '{"client_id":"alice","tier":"free"}' | grep -i retry-after # Retry-After: 1
curl -s -X POST localhost:8000/v1/check -H 'content-type: application/json' \
  -d '{"client_id":"alice","tier":"gold"}'                       # {"error":"unknown_tier"}
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/v1/check # 405
```

## 5. Custom tiers (FR-014a)

```bash
echo '{"basic": {"capacity": 3, "refill_rate": 0.5}}' > /tmp/tiers.json
RATELIMITER_TIERS_FILE=/tmp/tiers.json .venv/bin/uvicorn ratelimiter.main:app --app-dir src
# "basic" works, "free" → 400 unknown_tier.
RATELIMITER_TIERS_FILE=/nonexistent .venv/bin/uvicorn ratelimiter.main:app --app-dir src
# expect: start-up fails with ConfigError.
```
