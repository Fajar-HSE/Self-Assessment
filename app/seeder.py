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

KKNI_FILE = Path(__file__).parent / "data" / "kkni_levels.json"


def seed():
    db = init_db()
    
    # Check if already fully seeded
    if db.query(CertificationScheme).count() > 0:
        print("✅ Database already seeded")
        db.close()
        return
    
    # Create certification types (idempotent)
    bnsp_type = db.query(CertificationType).filter_by(name="Sertifikasi BNSP").first()
    if not bnsp_type:
        bnsp_type = CertificationType(
            name="Sertifikasi BNSP",
            description="Sertifikasi kompetensi resmi Badan Nasional Sertifikasi Profesi"
        )
        db.add(bnsp_type)
        db.commit()
    
    # Load KKNI data
    try:
        with open(KKNI_FILE) as f:
            kkni = json.load(f)
    except FileNotFoundError:
        print("⚠️ KKNI data file not found, using inline fallback")
        kkni = _get_fallback_data()
    
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


def _get_fallback_data() -> dict:
    """Inline fallback when kkni_levels.json not found."""
    schemes = {}
    # 40 fallback schemes covering all levels 1-9
    fallback = [
        ("Skema Operator Mesin Produksi", 1, "Operator Dasar", "industri"),
        ("Skema Pembantu Teknisi Laboratorium", 1, "Operator Dasar", "lingkungan"),
        ("Skema Pramu Bakti Industri", 2, "Operator Dasar", "pelayanan"),
        ("Skema Pramuniaga", 2, "Operator Dasar", "pemasaran"),
        ("Skema Administrasi Perkantoran Junior", 2, "Operator Dasar", "administrasi"),
        ("Skema Teknisi Akuntansi Junior", 3, "Operator Terampil", "akuntansi"),
        ("Skema Teknisi Perpajakan Junior", 3, "Operator Terampil", "akuntansi"),
        ("Skema K3 Umum", 3, "Operator Terampil", "k3"),
        ("Skema Petugas P3K di Tempat Kerja", 3, "Operator Terampil", "k3"),
        ("Skema Operator Komputer Junior", 3, "Operator Terampil", "teknologi-informasi"),
        ("Skema Digital Marketing Junior", 3, "Operator Terampil", "pemasaran"),
        ("Skema Teknisi Lingkungan", 4, "Teknisi Terampil", "lingkungan"),
        ("Skema Teknisi K3 Muda", 4, "Teknisi Terampil", "k3"),
        ("Skema Teknisi Akuntansi Madya", 4, "Teknisi Terampil", "akuntansi"),
        ("Skema Teknisi Perpajakan Madya", 4, "Teknisi Terampil", "akuntansi"),
        ("Skema Pengelola Limbah Industri", 4, "Teknisi Terampil", "lingkungan"),
        ("Skema Analis Data Junior", 4, "Teknisi Terampil", "teknologi-informasi"),
        ("Skema Marketing Officer", 4, "Teknisi Terampil", "pemasaran"),
        ("Skema SDM Junior", 4, "Teknisi Terampil", "administrasi"),
        ("Skema Teknisi Akuntansi Senior", 5, "Teknisi/Analis Madya", "akuntansi"),
        ("Skema Auditor Internal", 5, "Teknisi/Analis Madya", "akuntansi"),
        ("Skema Ahli K3 Muda", 5, "Teknisi/Analis Madya", "k3"),
        ("Skema Analis Pengelolaan Lingkungan", 5, "Teknisi/Analis Madya", "lingkungan"),
        ("Skema Supervisor Administrasi", 5, "Teknisi/Analis Madya", "administrasi"),
        ("Skema IT Project Coordinator", 5, "Teknisi/Analis Madya", "teknologi-informasi"),
        ("Skema Ahli Pratama K3", 6, "Ahli Pratama", "k3"),
        ("Skema Analis Perpajakan Senior", 6, "Ahli Pratama", "akuntansi"),
        ("Skema Manajer Lingkungan", 6, "Ahli Pratama", "lingkungan"),
        ("Skema Manajer SDM", 6, "Ahli Pratama", "administrasi"),
        ("Skema IT Manager", 6, "Ahli Pratama", "teknologi-informasi"),
        ("Skema Ahli Madya K3", 7, "Ahli Madya", "k3"),
        ("Skema Konsultan Pajak", 7, "Ahli Madya", "akuntansi"),
        ("Skema Manajer Keuangan", 7, "Ahli Madya", "akuntansi"),
        ("Skema Konsultan Lingkungan", 7, "Ahli Madya", "lingkungan"),
        ("Skema Konsultan SDM", 7, "Ahli Madya", "administrasi"),
        ("Skema Ahli Utama K3", 8, "Ahli Utama", "k3"),
        ("Skema Konsultan Manajemen Senior", 8, "Ahli Utama", "administrasi"),
        ("Skema Analis Kebijakan Publik", 8, "Ahli Utama", "administrasi"),
        ("Skema Ahli Paripurna K3", 9, "Ahli Paripurna", "k3"),
        ("Skema Kepala Badan/Organisasi", 9, "Ahli Paripurna", "administrasi"),
    ]
    for name, level, jenjang, bidang in fallback:
        schemes[name] = {
            "kkni_level": level,
            "jenjang": jenjang,
            "bidang": bidang,
            "keyword": [name.lower()],
            "next_level": []
        }
    return {"skema_levels": schemes}


if __name__ == "__main__":
    seed()
