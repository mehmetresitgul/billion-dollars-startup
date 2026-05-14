# Pacifor AI

FastAPI + LangGraph ile yazılmış MVP AI agent sistemi.
Kill switch, HITL (Human-in-the-Loop) gate ve audit logger içerir.

---

## Proje Durumu

| Bileşen | Durum |
|---|---|
| Kill switch | Implement edildi, 26 unit test |
| Audit logger | Implement edildi, 41 unit test |
| HITL gate | Implement edildi, 26 unit test |
| Guard decorator | Implement edildi, 16 unit test |
| Graph (planner→reviewer→executor) | Implement edildi, 26 unit test |
| FastAPI routes (/runs, /hitl, /kill, /audit) | Skeleton hazır, servis katmanı in-memory |
| DB persistence (SQLAlchemy async) | Model'lar hazır, migration'lar yazılmadı |
| Redis (distributed kill switch) | Kod hazır, opsiyonel |

**Toplam: 136 test, 0 failure**

---

## Klasör Yapısı

```
pacifor-ai/
├── pyproject.toml
├── .env.example
├── src/pacifor/
│   ├── main.py                        # FastAPI app factory, lifespan hooks
│   ├── core/
│   │   ├── config.py                  # pydantic-settings (.env okur)
│   │   ├── db.py                      # async SQLAlchemy engine + get_session
│   │   ├── redis_client.py            # aioredis bağlantısı (None fallback)
│   │   ├── kill_switch.py             # KillSwitch sınıfı ← ana mekanizma
│   │   ├── audit.py                   # AuditLogger + AuditEvent (frozen dataclass)
│   │   ├── hashing.py                 # SHA-256 payload hash
│   │   └── exceptions.py             # KillSwitchEngaged, HITLRejected, RunNotFound
│   ├── agents/
│   │   ├── state.py                   # AgentState TypedDict
│   │   ├── graph.py                   # build_graph() → StateGraph + MemorySaver
│   │   ├── guards.py                  # make_guard(ks, logger) + guard decorator
│   │   ├── hitl.py                    # hitl_gate() → interrupt() + audit
│   │   └── nodes/
│   │       ├── planner.py             # @guard, mesajdan plan üretir
│   │       ├── reviewer.py            # @guard + hitl_gate (HITL noktası)
│   │       └── executor.py            # @guard, planı çalıştırır
│   ├── api/
│   │   ├── routes/
│   │   │   ├── runs.py                # POST /v1/runs, GET /v1/runs/{id}
│   │   │   ├── hitl.py                # GET /v1/hitl/pending, POST /v1/hitl/{id}/approve|reject
│   │   │   ├── kill_switch.py         # POST /v1/kill, POST /v1/kill/release, GET /v1/kill/status
│   │   │   └── audit.py               # GET /v1/audit
│   │   └── schemas/                   # Pydantic request/response modelleri
│   ├── models/                        # SQLAlchemy ORM (Run, AuditEntry, HITLReview, KillEvent)
│   └── services/
│       ├── run_service.py             # Graph'ı background task olarak çalıştırır (in-memory)
│       ├── hitl_service.py            # Pending review'ları tutar, graph'ı resume eder
│       └── kill_service.py            # KillSwitch + audit entegrasyonu
└── tests/
    └── unit/
        ├── test_kill_switch.py        # 26 test
        ├── test_audit.py              # 41 test
        ├── test_guards.py             # 16 test
        ├── test_hitl.py               # 26 test
        └── test_graph.py              # 27 test
```

---

## Kurulum

```bash
cd pacifor-ai
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -e ".[dev]"

cp .env.example .env
# .env içinde OPENAI_API_KEY'i doldur
```

### Sunucuyu çalıştır

```bash
uvicorn pacifor.main:app --reload
# http://localhost:8000/docs  → Swagger UI
```

### Testleri çalıştır

```bash
pytest tests/unit/ -v
```

---

## 3 Temel Mekanizma

### 1. Kill Switch

```
POST /v1/kill           {"reason": "emergency"}   → tüm agent'lar durur
POST /v1/kill/release   {}                         → normal operasyon
GET  /v1/kill/status                               → {"engaged": bool}
```

**Nasıl çalışır:**
- Her LangGraph node'u `@guard` decorator'ı ile korunur
- `@guard` node'un ilk satırında `kill_switch.check()` çağırır
- Engaged ise `KillSwitchEngaged` raise eder, node çalışmaz
- Redis varsa dağıtık (tüm pod'lar durur); yoksa `asyncio.Event` fallback
- Engage sırasında Redis hata verirse local state güvenli kalır

**Test için:**
```python
from pacifor.core.kill_switch import kill_switch
await kill_switch.engage(reason="test")
await kill_switch.release()
```

### 2. HITL Gate

```
GET  /v1/hitl/pending              → bekleyen review listesi
POST /v1/hitl/{id}/approve  {"approved": true,  "decided_by": "ops"}
POST /v1/hitl/{id}/reject   {"approved": false, "reason": "risky"}
```

**Nasıl çalışır:**
- `reviewer_node` → `hitl_gate()` → LangGraph `interrupt()` ile graph duraklar
- `interrupt()` ilk çağrıda `GraphInterrupt` raise eder (graph pause)
- Human API'dan approve/reject gönderir
- `run_service.resume()` → `graph.ainvoke(Command(resume=decision))` ile graph devam eder
- `approved=False` veya geçersiz decision → `HITLRejected` raise edilir (safety default)

**HITL gate'i test için:**
```python
# interrupt() patch'le, graph'ı tek invoke'da tamamla
with patch("pacifor.agents.hitl.interrupt", return_value={"approved": True}):
    result = await graph.ainvoke(state, config=config)
```

### 3. Audit Logger

Her node, HITL kararı ve kill switch olayı `audit_logger.emit()` üzerinden geçer.

```python
AuditEvent.build(
    run_id="...",
    node_name="planner",
    action="plan",
    outcome="success",
    payload={"plan_length": 42},   # sadece hash saklanır, ham veri değil
)
```

**Sorgulama:**
```python
# In-memory buffer (son 500 event)
audit_logger.filter(run_id="abc", action="hitl_decision")
audit_logger.recent(limit=10)

# DB (GET /v1/audit?run_id=abc&node_name=planner)
```

---

## Agent Graph Akışı

```
planner_node
  ↓  plan üretir
reviewer_node        ← HITL gate (human approve/reject)
  ↓  approved
executor_node
  ↓
END
```

Her node:
1. `@guard` → kill switch check
2. İş mantığı
3. `audit_logger.emit()` → stdout JSON + optional DB
4. Partial state update döner (`{"plan": ...}` gibi, `{**state, ...}` değil)

---

## Sonraki Adımlar

Yapılacaklar (öncelik sırasıyla):

1. **LLM entegrasyonu** — `planner_node`'da `ChatOpenAI.ainvoke(messages)` ekle
2. **DB persistence** — `run_service` ve `hitl_service`'i in-memory dict'ten SQLAlchemy'e taşı
3. **Alembic migration** — `alembic init migrations`, `alembic revision --autogenerate`
4. **HITL graph resume** — `hitl_service.decide()` gerçekten `Command(resume=...)` çalıştırsın
5. **Integration testleri** — `tests/integration/test_hitl_api.py`, `test_runs_api.py`
6. **Auth** — `POST /v1/kill` ve `/v1/hitl` endpoint'leri korunsun
7. **Executor tool'ları** — gerçek aksiyonlar (web search, code exec, API call vb.)

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./pacifor.db` | Async SQLAlchemy URL |
| `REDIS_URL` | `None` | Boş bırakılırsa kill switch local mode'da çalışır |
| `OPENAI_API_KEY` | — | Planner LLM çağrısı için (henüz stub) |
| `KILL_SWITCH_TTL_SECONDS` | `3600` | Redis key TTL |
| `DEBUG` | `false` | SQLAlchemy echo + log level |

---

## Geliştirme Notları

- `make_guard(ks, logger)` factory'yi test'lerde kullan, global singleton'ı kirletme
- `hitl_gate()` `logger=` kwarg'ı alır — testlerde inject et
- `audit_logger.filter(run_id=..., action=...)` assertion için in-memory buffer'ı kullan
- Node'lar partial state döner (`{"plan": x}`) — `{**state, "plan": x}` değil; messages reducer'ı bozar
- Graph checkpointer olmadan `interrupt()` runtime'da patlar — `build_graph()` her zaman `MemorySaver` kullanır
