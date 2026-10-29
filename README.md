# 🏥 Q-Transplant v4 — National Organ Transplant Allocation & Intelligence System

> **Mini Project 2026** | Department of Computer Science & Engineering  
> A fully-integrated clinical platform for intelligent organ matching, real-time ischemia tracking, GIS logistics, and AI-assisted transplant coordination.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

---

## 🌐 Live Demo

After running locally, access at: `http://localhost:8000`

---

## 🚀 Features

### 🔴 Real-Time Organ Viability Decay Engine
- Heart: **4 hours** cold ischemia
- Lung: **6 hours**
- Liver/Pancreas: **12 hours**
- Kidney: **24 hours**
- Live countdown timer and viability % per organ

### 🗺️ GIS Transport Logistics
- Haversine geodesic distance between donor and recipient hospitals
- Ground ambulance vs air-lift routing with decay modeling
- Estimated time-of-arrival integrated into match scoring

### 🧬 6-Locus HLA Crossmatch Engine
- Full HLA-A, B, C, DR, DQ, DP antigen typing
- Panel-Reactive Antibody (PRA%) compatibility scoring
- Forbidden antigen mismatch detection with penalty tiers

### 🤖 OrganPulse AI Clinical Assistant
- Groq LLaMA 3.1 powered (with deterministic fallback)
- Answers clinical, technical, and operational queries
- Context-aware responses about Q-Transplant workflows

### 🔐 SHA-256 Tamper-Evident Audit Ledger
- Cryptographic blockchain-style chaining
- Every donor registration and match decision recorded
- Immutable audit trail for regulatory compliance

### 📊 System Relational Database Explorer (Root Organizer Only)
- Live SQL table inspector from the UI
- Hospital-wise donor dataset viewer
- Excel/CSV export for all datasets

### 🏥 Multi-Hospital Architecture
- Hospital role: Register donors, search recipients, view matches
- Root organizer role: View all data, export, audit, monitor

---

## 🏗️ Architecture

```
Q-Transplant/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── auth.py              # JWT authentication
│   │   ├── database.py          # DB connection & session
│   │   ├── routers/
│   │   │   ├── donors.py        # Donor CRUD + viability
│   │   │   ├── organizer.py     # Root organizer endpoints
│   │   │   ├── recipients.py    # Recipient matching
│   │   │   ├── hospitals.py     # Hospital management
│   │   │   └── assistant.py     # OrganPulse AI chat
│   │   └── services/
│   │       ├── matching.py      # HLA + GIS match engine
│   │       ├── viability.py     # Ischemia decay engine
│   │       └── groq_assistant.py # AI assistant service
│   └── public/
│       └── index.html           # Full SPA frontend
├── requirements.txt
└── README.md
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/Aravindh-coder/Q-transplant-mini-project2026.git
cd Q-transplant-mini-project2026

# Install dependencies
pip install -r backend/requirements.txt

# Start the server
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Access the Application
- **Frontend SPA**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🔑 Default Credentials

| Role | Email | Password |
|------|-------|----------|
| Root Organizer | `root@qtransplant.org` | `root123` |
| Hospital 1 | Register via UI | — |
| Hospital 2 | Register via UI | — |

---

## 📡 Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | JWT Authentication |
| `POST` | `/api/v1/donors/register` | Register new donor |
| `GET` | `/api/v1/donors/search` | Search donors by criteria |
| `POST` | `/api/v1/recipients/register` | Register recipient |
| `GET` | `/api/v1/recipients/match/{id}` | Run compatibility match |
| `GET` | `/api/v1/organizer/full-database-dump` | View all datasets (Root) |
| `GET` | `/api/v1/organizer/export-donors-csv` | Export CSV (Root) |
| `POST` | `/api/v1/assistant/chat` | OrganPulse AI chat |

---

## 🧪 Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.11) |
| Database | SQLite + SQLAlchemy ORM |
| Authentication | JWT (RS256) |
| AI Assistant | Groq LLaMA 3.1 + Deterministic Fallback |
| Frontend | Vanilla JS + CSS (Claymorphism SPA) |
| Cryptography | SHA-256 Audit Ledger |
| GIS | Haversine Formula |

---

## 👥 Team

- **Developer**: Aravindh (Aravindh-coder)
- **Institution**: [Your College Name]
- **Project Type**: Mini Project 2026

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Q-Transplant v4</strong> — Saving lives through intelligent organ allocation 🏥❤️
</p>
