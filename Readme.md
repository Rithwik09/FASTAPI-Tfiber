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

