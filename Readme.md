pip install fastapi uvicorn requests python-dotenv


folder Structure
backend/
│
├── main.py
├── services/
│   ├── status_service.py
│   ├── filter_service.py
|   └── refresh_service.py
│
├── models/
│   └── request_models.py
│
└── cache/
    └── status_cache.py

The Ideal Flow 

User
 ↓
Flowise
 ↓
Groq
 ↓
FastAPI
 ↓
In-Memory Cache
 ↓
TFiber Status API

app/

routers/
    resolver.py
    status.py
    topology.py
    service.py

services/
    resolver_service.py
    status_service.py
    topology_service.py
    service_status_service.py

neo4j/
    connection.py
    district_queries.py
    device_queries.py
    service_queries.py
    topology_queries.py

models/
    request_models.py
    response_models.py

utils/
    compression.py