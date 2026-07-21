"""
Seed database with KKNI data from existing knowledge_base
"""
import json
import sys
from pathlib import Path

from .database import (
    init_db, SessionLocal,
    CertificationType, CertificationScheme, CompetencyUnit,
    CompetencyElement, PerformanceCriteria, SchemeUnit,
)

KKNI_FILE = Path(__file__).parent.parent.parent / "knowledge_base" / "kkni_levels.json"


def seed():
    db = init_db()
    
    # Check if already seeded
    if db.query(CertificationScheme).count() > 0:
        print("✅ Database already seeded")
        return
    
    # Create certification types
    bnsp_type = CertificationType(
        name="Sertifikasi BNSP",
        description="Sertifikasi kompetensi resmi Badan Nasional Sertifikasi Profesi"
    )
    db.add(bnsp_type)
    db.commit()
    
    # Load KKNI data
    with open(KKNI_FILE) as f:
        kkni = json.load(f)
    
    skema_list = kkni.get("skema_levels", {})
    count = 0
    
    for skema_name, skema_info in skema_list.items():
        scheme = CertificationScheme(
            name=skema_name,
            type_id=bnsp_type.id,
            kkni_level=skema_info.get("kkni_level", 3),
            kkni_jenjang=skema_info.get("jenjang", ""),
            bidang=skema_info.get("bidang", ""),
            keywords=skema_info.get("keyword", []),
            description=f"Skema sertifikasi {skema_name} — KKNI Level {skema_info.get('kkni_level', 3)}",
        )
        db.add(scheme)
        
        # Create competency units for each scheme
        unit = CompetencyUnit(
            code=f"UK.{count+1:02d}",
            title=f"Kompetensi {skema_name}",
            description=f"Unit kompetensi untuk {skema_name} sesuai SKKNI bidang {skema_info.get('bidang', '')}"
        )
        db.add(unit)
        db.commit()
        
        # Link scheme ↔ unit
        su = SchemeUnit(scheme_id=scheme.id, unit_id=unit.id)
        db.add(su)
        
        # Create competency elements with KUK
        for elem_idx in range(1, 4):  # 3 elements per unit
            elem = CompetencyElement(
                unit_id=unit.id,
                code=f"E{elem_idx:02d}",
                title=f"Elemen {elem_idx}: {_get_element_title(elem_idx, skema_info.get('bidang', ''))}",
                order=elem_idx,
                weight=1.0,
            )
            db.add(elem)
            db.commit()
            
            # 3 KUK per element
            for kuk_idx in range(1, 4):
                kuk = PerformanceCriteria(
                    element_id=elem.id,
                    code=f"KUK{kuk_idx:02d}",
                    criterion=_get_kuk_text(count, elem_idx, kuk_idx, skema_name, skema_info.get('bidang', '')),
                    competence_type="knowledge" if elem_idx == 1 else ("skill" if elem_idx == 2 else "attitude"),
                    difficulty=elem_idx,
                )
                db.add(kuk)
        
        count += 1
        
        if count % 10 == 0:
            db.commit()
            print(f"  Seeded {count}/{len(skema_list)} schemes...")
    
    db.commit()
    print(f"✅ Seeded {count} schemes with units, elements, and KUKs")


def _get_element_title(idx: int, bidang: str) -> str:
    titles = {
        1: f"Pengetahuan Dasar {bidang or 'Kompetensi'}",
        2: f"Penerapan Praktis {bidang or 'Kompetensi'}",
        3: f"Sikap Kerja dan Profesionalisme",
    }
    return titles.get(idx, f"Aspek Kompetensi {idx}")


def _get_kuk_text(scheme_idx: int, elem_idx: int, kuk_idx: int, skema: str, bidang: str) -> str:
    templates = [
        [
            f"Mengidentifikasi prinsip dasar {bidang or 'kompetensi'} sesuai standar industri",
            f"Menjelaskan regulasi dan peraturan terkait {bidang or 'kompetensi'} yang berlaku",
            f"Mendeskripsikan prosedur operasional standar di bidang {bidang or 'kompetensi'}",
        ],
        [
            f"Menerapkan teknik dan metode {bidang or 'kompetensi'} dalam pekerjaan sehari-hari",
            f"Menggunakan peralatan dan instrumen yang sesuai untuk tugas {bidang or 'kompetensi'}",
            f"Mendokumentasikan dan melaporkan hasil kerja sesuai prosedur",
        ],
        [
            f"Menunjukkan integritas dan tanggung jawab dalam pelaksanaan tugas",
            f"Berkomunikasi efektif dengan tim dan pemangku kepentingan",
            f"Melakukan evaluasi diri dan pengembangan kompetensi berkelanjutan",
        ],
    ]
    return templates[elem_idx-1][kuk_idx-1]


if __name__ == "__main__":
    seed()
