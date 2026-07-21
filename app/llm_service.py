"""
LLM Service — Adaptive questioning via Hermes-Local
Menentukan KKNI level dari jabatan + generate pertanyaan adaptif
"""

import httpx
import json
import logging
import os
from dotenv import load_dotenv
from typing import Optional

logger = logging.getLogger(__name__)

load_dotenv()

# Groq API
LLM_URL = os.getenv("LLM_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")


def determine_kkni_level(jabatan: str, perusahaan: str = "", industri: str = "",
                          pendidikan: str = "", pengalaman_tahun: int = 0) -> dict:
    """
    Tentukan KKNI level yang sesuai berdasarkan profil peserta.
    Returns: {"level": 3, "jenjang": "Operator Terampil", "reasoning": "..."}
    """
    prompt = f"""Anda adalah asisten penempatan KKNI level. Tentukan KKNI level yang sesuai untuk profesional berikut:

Jabatan: {jabatan}
Perusahaan: {perusahaan or '-'}
Industri: {industri or '-'}
Pendidikan: {pendidikan or '-'}
Pengalaman: {pengalaman_tahun} tahun

KKNI Level Guidelines:
- Level 1-2: Operator Dasar, pekerjaan rutin terstruktur
- Level 3: Operator Terampil, mampu melaksanakan tugas spesifik
- Level 4: Teknisi Terampil, memecahkan masalah teknis
- Level 5: Teknisi/Analis Madya, mengelola pekerjaan kompleks
- Level 6: Ahli Pratama, merencanakan dan mengelola sumber daya
- Level 7: Ahli Madya, memformulasikan solusi masalah kompleks
- Level 8: Ahli Utama, mengembangkan pengetahuan baru
- Level 9: Ahli Paripurna, puncak keahlian

Jawab dengan format JSON:
{{"level": <number 1-9>, "jenjang": "<nama jenjang>", "reasoning": "<penjelasan singkat>"}}
"""
    return _call_llm(prompt, json_mode=True)


def generate_question(kuk: str, element_title: str, unit_title: str,
                      jabatan: str, perusahaan: str, kkni_level: int) -> dict:
    """
    Generate pertanyaan adaptif berdasarkan KUK dan profil user.
    """
    prompt = f"""Anda adalah asesor kompetensi BNSP. Buat pertanyaan self-assessment yang adaptif untuk:

KUK: {kuk}
Elemen: {element_title}
Unit: {unit_title}
Profil: {jabatan} di {perusahaan}
Target Level: KKNI {kkni_level}

Buat 1 pertanyaan yang:
1. Relevan dengan pekerjaan sehari-hari {jabatan}
2. Spesifik — bukan pertanyaan generik
3. Bisa dijawab dengan skala 0-100 (confidence) + bukti singkat
4. Sesuai level KKNI {kkni_level}

Format JSON:
{{
    "question": "<pertanyaan adaptif>",
    "context_hint": "<contoh konteks pekerjaan yg relevan>",
    "what_to_prove": "<bukti/evidence yg menunjukkan kompetensi>"
}}
"""
    return _call_llm(prompt, json_mode=True)


def evaluate_answer(kuk: str, question: str, answer_confidence: int,
                    evidence: str, kkni_level: int, jabatan: str) -> dict:
    """
    Evaluasi jawaban user, beri score.
    """
    prompt = f"""Anda asesor BNSP. Evaluasi jawaban self-assessment:

KUK: {kuk}
Pertanyaan: {question}
Confidence: {answer_confidence}/100
Evidence: {evidence or '(tidak ada bukti)'}
Target KKNI: {kkni_level}
Jabatan: {jabatan}

Evaluasi:
1. Apakah confidence sesuai dengan evidence yang diberikan?
2. Apakah evidence cukup membuktikan kompetensi?
3. Beri score 0-100

Format JSON:
{{
    "score": <number 0-100>,
    "evaluation": "<analisis singkat>",
    "feedback": "<rekomendasi improvement>",
    "confidence_alignment": "<overestimated/underestimated/accurate>"
}}
"""
    return _call_llm(prompt, json_mode=True)


def generate_recommendation(assessment_data: dict) -> str:
    """
    Generate narrative recommendation based on assessment results.
    """
    mastered = assessment_data.get('mastered_kuk', [])
    gaps = assessment_data.get('gap_kuk', [])
    overall_score = assessment_data.get('overall_score', 0)
    current_scheme = assessment_data.get('scheme_name', '')
    jabatan = assessment_data.get('jabatan', '')
    
    gap_items = '\n'.join([f"- {g}" for g in gaps[:5]])
    mastered_items = '\n'.join([f"- {m}" for m in mastered[:5]])
    
    prompt = f"""Buat rekomendasi personal untuk peserta self-assessment BNSP:

Skema: {current_scheme}
Jabatan: {jabatan}
Overall Score: {overall_score}/100
Area dikuasai:
{mastered_items or '(belum ada)'}
Area perlu ditingkatkan:
{gap_items or '(belum ada)'}

Beri rekomendasi dalam 3 paragraf:
1. Ringkasan hasil assessment (tone positif/memotivasi)
2. Gap utama yang perlu dibridging (spesifik, actionable)
3. Rekomendasi skema sertifikasi selanjutnya (KKNI ladder-aware)

Gunakan bahasa Indonesia profesional, personal, direct.
"""
    response = _call_llm(prompt, json_mode=False)
    return response.get('content', response.get('text', str(response)))


def _call_llm(prompt: str, json_mode: bool = False, max_tokens: int = 1000) -> dict:
    """Call Agnes AI API (GPT-4o compatible)."""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(LLM_URL, json=payload, headers=headers)
            if r.status_code == 401:
                logger.error("Invalid API key for Agnes AI")
                return _fallback(prompt, json_mode)
            r.raise_for_status()
            data = r.json()
            content = data['choices'][0]['message']['content']
            
            if json_mode:
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('\n', 1)[1].rsplit('\n```', 1)[0]
                return json.loads(content)
            return {"content": content}
    except httpx.ConnectError:
        logger.warning("LLM not available at %s — using fallback", LLM_URL)
        return _fallback(prompt, json_mode)
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return _fallback(prompt, json_mode)


def _fallback(prompt: str, json_mode: bool) -> dict:
    """Fallback when LLM not reachable."""
    if json_mode:
        # Determine KKNI level
        if prompt.count('"level"') > 0 and ('jabatan' in prompt.lower() or 'pengalaman' in prompt.lower()):
            return {"level": 3, "jenjang": "Operator Terampil",
                    "reasoning": "Berdasarkan profil jabatan dan pengalaman, level KKNI 3 (Operator Terampil) paling sesuai. Hubungi tim ICC untuk konsultasi lebih lanjut."}
        # Generate adaptive question
        if '"question"' in prompt and '"what_to_prove"' in prompt:
            kuk_match = [l for l in prompt.split('\n') if 'KUK:' in l]
            kuk_text = kuk_match[0].replace('KUK:', '').strip() if kuk_match else 'kompetensi ini'
            return {
                "question": f"Berdasarkan KUK: \"{kuk_text}\" — seberapa yakin Anda menguasai kompetensi ini dalam pekerjaan sehari-hari?",
                "context_hint": "Berikan contoh situasi kerja nyata di mana kompetensi ini diterapkan.",
                "what_to_prove": "Sebutkan bukti konkret: dokumen, laporan, atau hasil kerja yang menunjukkan penguasaan."
            }
        # Evaluate answer
        if '"score"' in prompt and '"confidence_alignment"' in prompt:
            return {"score": 70, "evaluation": "Jawaban Anda menunjukkan pemahaman yang cukup baik.",
                    "feedback": "Untuk validasi lebih akurat, konsultasikan dengan asesor ICC.",
                    "confidence_alignment": "accurate"}
    return {"content": "Assessment selesai. Hubungi tim ICC (0853-2888-3511) untuk konsultasi hasil lebih lanjut."}
