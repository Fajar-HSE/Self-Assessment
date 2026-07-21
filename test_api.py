"""Test self-assessment API endpoints"""
import sys, os, json, time, subprocess, httpx

# Clean path
os.environ["PYTHONPATH"] = ""
for key in list(os.environ.keys()):
    if 'hermes' in key.lower():
        del os.environ[key]

venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'python.exe')
run_py = os.path.join(os.path.dirname(__file__), 'run.py')

# Start server
proc = subprocess.Popen(
    [venv_python, run_py],
    cwd=os.path.dirname(__file__),
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
time.sleep(4)

try:
    base = "http://localhost:8020"
    
    # 1. Home
    r = httpx.get(f"{base}/", timeout=10)
    print(f"GET /: {r.status_code}")
    
    # 2. List schemes
    r = httpx.get(f"{base}/api/schemes", timeout=10)
    print(f"GET /api/schemes: {r.status_code}")
    data = r.json()
    print(f"  Total schemes: {len(data)}")
    if data:
        print(f"  First: {data[0]['name']} — Level {data[0]['kkni_level']}")
    
    # 3. Scheme detail
    if data:
        scheme_id = data[0]['id']
        r = httpx.get(f"{base}/api/schemes/{scheme_id}", timeout=10)
        print(f"\nGET /api/schemes/{scheme_id}: {r.status_code}")
        s = r.json()
        print(f"  {s['name']} — {len(s['units'])} unit(s)")
        total_kuk = 0
        for u in s['units']:
            for e in u['elements']:
                total_kuk += len(e['criteria'])
        print(f"  Total KUK in scheme: {total_kuk}")
    
    # 4. Determine level
    r = httpx.post(f"{base}/api/determine-level", json={
        "jabatan": "HSE Supervisor",
        "perusahaan": "PT Pertamina",
        "industri": "k3",
        "pendidikan": "S1",
        "pengalaman_tahun": 5,
    }, timeout=15)
    print(f"\nPOST /api/determine-level: {r.status_code}")
    level = r.json()
    print(f"  Level: {level['level']} — {level['jenjang']}")
    print(f"  Schemes: {[s['name'] for s in level['schemes']]}")
    
    # 5. Create user
    r = httpx.post(f"{base}/api/users", json={
        "name": "Fajar Testing",
        "email": "test@icc.com",
        "jabatan": "HSE Supervisor",
        "perusahaan": "PT Pertamina",
        "industri": "k3",
        "pengalaman_tahun": 5,
    }, timeout=10)
    print(f"\nPOST /api/users: {r.status_code}")
    user = r.json()
    print(f"  User ID: {user['id']}")
    
    # 6. Start assessment
    if level['schemes']:
        r = httpx.post(f"{base}/api/assessments", json={
            "user_id": user['id'],
            "scheme_id": level['schemes'][0]['id'],
        }, timeout=15)
        print(f"\nPOST /api/assessments: {r.status_code}")
        ass = r.json()
        print(f"  Assessment ID: {ass['assessment_id']}")
        q = ass.get('next_question')
        if q:
            print(f"  First question: {str(q.get('question', ''))[:80]}...")
            print(f"  Progress: {q['progress']['answered']}/{q['progress']['total']}")
        
        # 7. Submit answers
        assessment_id = ass['assessment_id']
        for i in range(min(3, q['progress']['total'] if q else 3)):
            if not q:
                break
            r = httpx.post(f"{base}/api/assessments/{assessment_id}/answer", json={
                "criterion_id": q['criterion_id'],
                "confidence": 75 + (i * 5),
                "evidence": f"Test evidence {i+1}",
                "question": q.get('question', ''),
            }, timeout=15)
            result = r.json()
            print(f"  Answer {i+1}: score={result.get('score', '?')}, status={result['status']}")
            if result['status'] == 'completed':
                break
            q = result.get('next_question')
        
        # 8. Get results
        r = httpx.get(f"{base}/api/assessments/{assessment_id}/results", timeout=15)
        print(f"\nGET results: {r.status_code}")
        results = r.json()
        print(f"  Overall score: {results['overall_score']}%")
        print(f"  Competent: {results['is_competent']}")
        print(f"  Mastered: {results['gap_summary']['mastered']}/{results['gap_summary']['total_kuk']}")
        print(f"  Gap: {results['gap_summary']['gap']}")
        print(f"  Next schemes: {len(results.get('next_schemes', []))}")
    
    print("\n✅ ALL TESTS PASSED")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()
