"""
Self-Assessment API Routes
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import (
    SessionLocal, init_db,
    CertificationType, CertificationScheme, CompetencyUnit,
    CompetencyElement, PerformanceCriteria, SchemeUnit,
    User, SelfAssessment, AssessmentAnswer, GapAnalysis
)
from .llm_service import determine_kkni_level, generate_question, evaluate_answer, generate_recommendation

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Schemes & Units ───

@router.get("/schemes")
def list_schemes(bidang: str = "", search: str = "", db: Session = Depends(get_db)):
    q = db.query(CertificationScheme)
    if bidang:
        q = q.filter(CertificationScheme.bidang == bidang)
    if search:
        q = q.filter(CertificationScheme.name.ilike(f"%{search}%"))
    schemes = q.order_by(CertificationScheme.kkni_level).all()
    return [{
        "id": s.id, "name": s.name, "kkni_level": s.kkni_level,
        "kkni_jenjang": s.kkni_jenjang, "bidang": s.bidang
    } for s in schemes]


@router.get("/schemes/{scheme_id}")
def get_scheme(scheme_id: int, db: Session = Depends(get_db)):
    scheme = db.query(CertificationScheme).filter(CertificationScheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    
    units = []
    for su in scheme.units:
        unit_data = {"id": su.unit.id, "code": su.unit.code, "title": su.unit.title, "elements": []}
        for elem in su.unit.elements:
            elem_data = {
                "id": elem.id, "code": elem.code, "title": elem.title,
                "weight": elem.weight, "criteria": []
            }
            for kuk in elem.criteria:
                elem_data["criteria"].append({
                    "id": kuk.id, "code": kuk.code, "criterion": kuk.criterion,
                    "competence_type": kuk.competence_type, "difficulty": kuk.difficulty
                })
            unit_data["elements"].append(elem_data)
        units.append(unit_data)
    
    return {
        "id": scheme.id, "name": scheme.name,
        "kkni_level": scheme.kkni_level, "kkni_jenjang": scheme.kkni_jenjang,
        "bidang": scheme.bidang, "description": scheme.description,
        "units": units
    }


# ─── LLM: Determine KKNI Level ───

@router.post("/determine-level")
def determine_level(data: dict, db: Session = Depends(get_db)):
    """Determine suggested KKNI level from job profile using LLM."""
    result = determine_kkni_level(
        jabatan=data.get("jabatan", ""),
        perusahaan=data.get("perusahaan", ""),
        industri=data.get("industri", ""),
        pendidikan=data.get("pendidikan", ""),
        pengalaman_tahun=data.get("pengalaman_tahun", 0),
    )
    # Find matching schemes
    level = result.get("level", 3)
    schemes = db.query(CertificationScheme).filter(
        CertificationScheme.kkni_level == level
    ).order_by(CertificationScheme.name).all()
    
    return {
        "level": level,
        "jenjang": result.get("jenjang", ""),
        "reasoning": result.get("reasoning", ""),
        "schemes": [{"id": s.id, "name": s.name, "bidang": s.bidang} for s in schemes],
        "all_levels": [
            {"level": 1, "jenjang": "Operator Dasar"},
            {"level": 2, "jenjang": "Operator Dasar"},
            {"level": 3, "jenjang": "Operator Terampil"},
            {"level": 4, "jenjang": "Teknisi Terampil"},
            {"level": 5, "jenjang": "Teknisi/Analis Madya"},
            {"level": 6, "jenjang": "Ahli Pratama"},
            {"level": 7, "jenjang": "Ahli Madya"},
            {"level": 8, "jenjang": "Ahli Utama"},
            {"level": 9, "jenjang": "Ahli Paripurna"},
        ]
    }


# ─── User & Assessment ───

@router.post("/users")
def create_user(data: dict, db: Session = Depends(get_db)):
    user = User(
        name=data.get("name", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        jabatan=data.get("jabatan", ""),
        perusahaan=data.get("perusahaan", ""),
        industri=data.get("industri", ""),
        pendidikan=data.get("pendidikan", ""),
        pengalaman_tahun=data.get("pengalaman_tahun", 0),
        expected_kkni_level=data.get("expected_kkni_level", 3),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name}


@router.post("/assessments")
def start_assessment(data: dict, db: Session = Depends(get_db)):
    """Start a new self-assessment session."""
    user_id = data.get("user_id")
    scheme_id = data.get("scheme_id")
    
    if not user_id or not scheme_id:
        raise HTTPException(400, "user_id and scheme_id required")
    
    assessment = SelfAssessment(
        user_id=user_id,
        scheme_id=scheme_id,
        status="in_progress",
        llm_context=data.get("llm_context"),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    
    # Return first question
    next_q = _get_next_question(db, assessment.id, user_id)
    return {"assessment_id": assessment.id, "next_question": next_q}


@router.get("/assessments/{assessment_id}/next")
def get_next_question(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(SelfAssessment).filter(SelfAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    
    q = _get_next_question(db, assessment_id, assessment.user_id)
    if q is None:
        # Assessment complete — generate results
        return {"status": "completed", "assessment_id": assessment_id}
    return {"status": "in_progress", "question": q}


def _get_next_question(db: Session, assessment_id: int, user_id: int) -> Optional[dict]:
    """Get next unanswered criterion, with LLM-adaptive question."""
    assessment = db.query(SelfAssessment).filter(SelfAssessment.id == assessment_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    
    # Get all KUK IDs for this scheme
    scheme_units = db.query(SchemeUnit).filter(SchemeUnit.scheme_id == assessment.scheme_id).all()
    unit_ids = [su.unit_id for su in scheme_units]
    
    all_criteria = db.query(PerformanceCriteria).join(CompetencyElement).filter(
        CompetencyElement.unit_id.in_(unit_ids)
    ).order_by(CompetencyElement.order, PerformanceCriteria.id).all()
    
    answered_criterion_ids = set()
    if assessment.answers:
        answered_criterion_ids = {a.criterion_id for a in assessment.answers}
    
    # Find first unanswered
    for kuk in all_criteria:
        if kuk.id not in answered_criterion_ids:
            elem = kuk.element
            unit = elem.unit
            
            # Try LLM-adaptive question (with fallback)
            try:
                llm_q = generate_question(
                    kuk=kuk.criterion,
                    element_title=elem.title,
                    unit_title=unit.title,
                    jabatan=user.jabatan if user else "",
                    perusahaan=user.perusahaan if user else "",
                    kkni_level=assessment.scheme.kkni_level if assessment.scheme else 3,
                )
                question = llm_q.get("question", kuk.criterion)
                context_hint = llm_q.get("context_hint", "")
                what_to_prove = llm_q.get("what_to_prove", "")
            except:
                question = f"Seberapa yakin Anda menguasai: {kuk.criterion}"
                context_hint = ""
                what_to_prove = ""
            
            return {
                "criterion_id": kuk.id,
                "unit_title": unit.title,
                "element_title": elem.title,
                "kuk_code": kuk.code,
                "kuk_text": kuk.criterion,
                "question": question,
                "context_hint": context_hint,
                "what_to_prove": what_to_prove,
                "competence_type": kuk.competence_type,
                "progress": {
                    "answered": len(answered_criterion_ids),
                    "total": len(all_criteria)
                }
            }
    return None


@router.post("/assessments/{assessment_id}/answer")
def submit_answer(assessment_id: int, data: dict, db: Session = Depends(get_db)):
    """Submit answer for a criterion."""
    assessment = db.query(SelfAssessment).filter(SelfAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    
    criterion_id = data.get("criterion_id")
    confidence = data.get("confidence", 50)
    evidence = data.get("evidence", "")
    
    criterion = db.query(PerformanceCriteria).filter(PerformanceCriteria.id == criterion_id).first()
    if not criterion:
        raise HTTPException(404, "Criterion not found")
    
    # LLM evaluation
    try:
        eval_result = evaluate_answer(
            kuk=criterion.criterion,
            question=data.get("question", ""),
            answer_confidence=confidence,
            evidence=evidence,
            kkni_level=assessment.scheme.kkni_level if assessment.scheme else 3,
            jabatan=assessment.user.jabatan if assessment.user else "",
        )
        score = eval_result.get("score", confidence)
        llm_eval = json.dumps(eval_result)
    except:
        score = confidence  # Fallback: confidence as score
        llm_eval = ""
    
    answer = AssessmentAnswer(
        assessment_id=assessment_id,
        criterion_id=criterion_id,
        confidence=confidence,
        evidence=evidence,
        llm_evaluation=llm_eval,
        score=score,
    )
    db.add(answer)
    db.commit()
    
    # Get next question
    next_q = _get_next_question(db, assessment_id, assessment.user_id)
    
    return {
        "status": "completed" if next_q is None else "in_progress",
        "answer_id": answer.id,
        "score": score,
        "next_question": next_q
    }


@router.get("/assessments/{assessment_id}/results")
def get_results(assessment_id: int, db: Session = Depends(get_db)):
    """Get full assessment results with gap analysis."""
    assessment = db.query(SelfAssessment).filter(SelfAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    
    # Get all criteria with answers
    scheme_units = db.query(SchemeUnit).filter(SchemeUnit.scheme_id == assessment.scheme_id).all()
    unit_ids = [su.unit_id for su in scheme_units]
    
    all_criteria = db.query(PerformanceCriteria).join(CompetencyElement).filter(
        CompetencyElement.unit_id.in_(unit_ids)
    ).order_by(CompetencyElement.order, PerformanceCriteria.id).all()
    
    # Build results per element
    elements_data = {}
    total_score = 0
    total_weight = 0
    
    for kuk in all_criteria:
        elem_id = kuk.element.id
        if elem_id not in elements_data:
            elements_data[elem_id] = {
                "element_code": kuk.element.code,
                "element_title": kuk.element.title,
                "weight": kuk.element.weight,
                "criteria": [],
                "element_score": 0,
                "count": 0
            }
        
        answer = db.query(AssessmentAnswer).filter(
            AssessmentAnswer.assessment_id == assessment_id,
            AssessmentAnswer.criterion_id == kuk.id
        ).first()
        
        kuk_data = {
            "id": kuk.id,
            "code": kuk.code,
            "criterion": kuk.criterion,
            "answered": answer is not None,
            "confidence": answer.confidence if answer else 0,
            "score": answer.score if answer else 0,
            "evidence": answer.evidence if answer else "",
        }
        elements_data[elem_id]["criteria"].append(kuk_data)
        
        if answer:
            elements_data[elem_id]["element_score"] += (answer.score or 0)
            elements_data[elem_id]["count"] += 1
    
    # Normalize element scores
    mastered_kuk = []
    gap_kuk = []
    result_elements = []
    
    for eid, edata in elements_data.items():
        if edata["count"] > 0:
            edata["element_score"] = round(edata["element_score"] / edata["count"], 1)
        total_score += edata["element_score"] * edata["weight"]
        total_weight += edata["weight"]
        
        result_elements.append(edata)
        
        for kuk in edata["criteria"]:
            if kuk["answered"] and (kuk["score"] or kuk["confidence"]) >= 70:
                mastered_kuk.append(kuk["criterion"])
            elif kuk["answered"]:
                gap_kuk.append(kuk["criterion"])
    
    overall_score = round(total_score / total_weight, 1) if total_weight > 0 else 0
    
    # Generate LLM recommendation
    rec = generate_recommendation({
        "mastered_kuk": mastered_kuk,
        "gap_kuk": gap_kuk,
        "overall_score": overall_score,
        "scheme_name": assessment.scheme.name if assessment.scheme else "",
        "jabatan": assessment.user.jabatan if assessment.user else "",
    })
    
    # Determine if competent
    threshold = 70
    is_competent = overall_score >= threshold
    
    # Recommend next schemes
    next_schemes = []
    if assessment.scheme:
        current_level = assessment.scheme.kkni_level
        next_schemes = db.query(CertificationScheme).filter(
            CertificationScheme.kkni_level > current_level,
            CertificationScheme.kkni_level <= current_level + 2,
            CertificationScheme.bidang == assessment.scheme.bidang,
        ).order_by(CertificationScheme.kkni_level).all()
    
    return {
        "assessment_id": assessment_id,
        "user": {"name": assessment.user.name, "jabatan": assessment.user.jabatan},
        "scheme": {"name": assessment.scheme.name, "kkni_level": assessment.scheme.kkni_level,
                    "kkni_jenjang": assessment.scheme.kkni_jenjang},
        "overall_score": overall_score,
        "is_competent": is_competent,
        "status": assessment.status,
        "elements": result_elements,
        "gap_summary": {
            "total_kuk": len(all_criteria),
            "mastered": len(mastered_kuk),
            "gap": len(gap_kuk),
            "unanswered": len(all_criteria) - len(mastered_kuk) - len(gap_kuk),
        },
        "mastered_kuk": mastered_kuk[:20],
        "gap_kuk": gap_kuk[:20],
        "recommendation": rec,
        "next_schemes": [{"id": s.id, "name": s.name, "kkni_level": s.kkni_level,
                           "kkni_jenjang": s.kkni_jenjang} for s in next_schemes[:5]],
        "cta": {
            "whatsapp": "0853-2888-3511",
            "email": "dwifajar15@gmail.com",
        }
    }
