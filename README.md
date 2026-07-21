# ICC Self-Assessment App

## Self-assessment kompetensi BNSP dengan adaptive AI

FastAPI + SQLite + Groq AI (LLaMA 3.3 70B)

## Stack
- Backend: FastAPI (Python)
- Database: SQLite via SQLAlchemy
- LLM: Groq API (llama-3.3-70b-versatile)
- Frontend: SPA HTML+CSS+JS (ICC Brand)

## Run
```bash
cd self-assessment
env -u PYTHONPATH ./venv/Scripts/python.exe run.py
```
Access: http://localhost:8020

## Architecture
CertificationType → CertificationScheme → SchemeUnit → CompetencyUnit → CompetencyElement → PerformanceCriteria(KUK) → AssessmentAnswer → SelfAssessment → User

## API Endpoints
- GET  /api/schemes — daftar skema
- GET  /api/schemes/{id} — detail skema + KUK
- POST /api/determine-level — LLM tentukan KKNI level dari jabatan
- POST /api/users — buat peserta
- POST /api/assessments — mulai sesi
- GET  /api/assessments/{id}/next — pertanyaan berikutnya
- POST /api/assessments/{id}/answer — submit jawaban
- GET  /api/assessments/{id}/results — hasil gap analysis
