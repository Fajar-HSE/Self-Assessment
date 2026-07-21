"""
Self-Assessment App — Database Schema
ICC Indonesian Certification Center

Architecture:
  CertificationType → CertificationScheme → Scheme_Units
  (junction) → CompetencyUnit → CompetencyElement → PerformanceCriteria (KUK)
  SelfAssessment ── AssessmentAnswer ── User
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timezone

# Support DATABASE_URL env var (Postgres on Vercel, SQLite locally)
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    connect_args = {"sslmode": "require"} if "amazonaws" in DATABASE_URL or "neon" in DATABASE_URL else {}
    engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)
else:
    # Use /tmp for Vercel (read-only fs) or local dir
    db_dir = "/tmp" if os.getenv("VERCEL") else os.path.dirname(__file__)
    DB_PATH = os.path.join(db_dir, 'self_assessment.db')
    engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


# ─── Master Data ───

class CertificationType(Base):
    """Jenis Sertifikasi: Sertifikasi BNSP, Sertifikasi Internasional, dll"""
    __tablename__ = 'certification_types'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    schemes = relationship("CertificationScheme", back_populates="type")


class CertificationScheme(Base):
    """Skema Sertifikasi: e.g. Skema Ahli K3 Umum BNSP"""
    __tablename__ = 'certification_schemes'
    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, unique=True)
    type_id = Column(Integer, ForeignKey('certification_types.id'))
    kkni_level = Column(Integer)
    kkni_jenjang = Column(String(100))
    bidang = Column(String(100))
    description = Column(Text)
    keywords = Column(JSON)  # List of search keywords
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    type = relationship("CertificationType", back_populates="schemes")
    units = relationship("SchemeUnit", back_populates="scheme")
    

class CompetencyUnit(Base):
    """Unit Kompetensi: e.g. UK.01 - Menerapkan Prosedur K3"""
    __tablename__ = 'competency_units'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True)  # UK.01
    title = Column(String(300), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    elements = relationship("CompetencyElement", back_populates="unit")
    schemes = relationship("SchemeUnit", back_populates="unit")


class SchemeUnit(Base):
    """Junction: many-to-many scheme ↔ unit"""
    __tablename__ = 'scheme_units'
    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey('certification_schemes.id'))
    unit_id = Column(Integer, ForeignKey('competency_units.id'))
    
    scheme = relationship("CertificationScheme", back_populates="units")
    unit = relationship("CompetencyUnit", back_populates="schemes")


class CompetencyElement(Base):
    """Elemen Kompetensi: bagian dari unit kompetensi"""
    __tablename__ = 'competency_elements'
    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey('competency_units.id'))
    code = Column(String(50))  # E01, E02
    title = Column(String(300), nullable=False)
    description = Column(Text)
    order = Column(Integer, default=0)
    weight = Column(Float, default=1.0)  # Bobot untuk scoring
    
    unit = relationship("CompetencyUnit", back_populates="elements")
    criteria = relationship("PerformanceCriteria", back_populates="element")


class PerformanceCriteria(Base):
    """Kriteria Unjuk Kerja (KUK) — pertanyaan assessment"""
    __tablename__ = 'performance_criteria'
    id = Column(Integer, primary_key=True)
    element_id = Column(Integer, ForeignKey('competency_elements.id'))
    code = Column(String(50))  # KUK01, KUK02
    criterion = Column(Text, nullable=False)  # The actual criterion text
    competence_type = Column(String(20), default='knowledge')  # knowledge/skill/attitude
    difficulty = Column(Integer, default=1)  # 1-5
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    element = relationship("CompetencyElement", back_populates="criteria")
    answers = relationship("AssessmentAnswer", back_populates="criterion")


# ─── Assessment Data ───

class User(Base):
    """User peserta assessment"""
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200))
    phone = Column(String(50))
    jabatan = Column(String(200))
    perusahaan = Column(String(300))
    industri = Column(String(200))
    pendidikan = Column(String(100))
    pengalaman_tahun = Column(Integer, default=0)
    expected_kkni_level = Column(Integer)  # LLM-determined
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    assessments = relationship("SelfAssessment", back_populates="user")


class SelfAssessment(Base):
    """Sesi self-assessment oleh user"""
    __tablename__ = 'self_assessments'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    scheme_id = Column(Integer, ForeignKey('certification_schemes.id'))
    status = Column(String(20), default='in_progress')  # in_progress, completed
    overall_score = Column(Float)  # 0-100
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    llm_context = Column(JSON)  # Adaptive context from LLM
    
    user = relationship("User", back_populates="assessments")
    scheme = relationship("CertificationScheme")
    answers = relationship("AssessmentAnswer", back_populates="assessment")


class AssessmentAnswer(Base):
    """Jawaban per KUK"""
    __tablename__ = 'assessment_answers'
    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey('self_assessments.id'))
    criterion_id = Column(Integer, ForeignKey('performance_criteria.id'))
    confidence = Column(Integer)  # 0-100 — seberapa yakin menguasai
    evidence = Column(Text)  # Bukti/dokumen pendukung
    llm_evaluation = Column(Text)  # Evaluasi adaptive dari LLM
    score = Column(Float)  # LLM-graded score
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    assessment = relationship("SelfAssessment", back_populates="answers")
    criterion = relationship("PerformanceCriteria", back_populates="answers")


# ─── Gap Analysis Result ───

class GapAnalysis(Base):
    """Hasil gap analysis per assessment"""
    __tablename__ = 'gap_analyses'
    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey('self_assessments.id'))
    summary = Column(Text)  # Overall narrative
    mastered_kuk = Column(JSON)  # List of KUK IDs mastered
    gap_kuk = Column(JSON)  # List of KUK IDs with gaps
    recommendations = Column(JSON)  # Recommended next schemes
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)
    return SessionLocal()


if __name__ == '__main__':
    init_db()
    print(f"✅ Database created at {DB_PATH}")
