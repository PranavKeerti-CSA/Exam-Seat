import re

with open('app/allocation_service.py', 'r') as f:
    content = f.read()

start_marker = "        # 1. Identify all eligible candidates taking subjects in this session"
end_marker = "        # Resilient fallback: if no candidate matched the session filter, seat all students"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    exit(1)

new_logic = """        # 1. Identify all eligible candidates taking subjects in this session
        
        # Priority mapping: lower number means higher priority. Primary subjects first.
        subject_priority = {
            "ENG": 1,
            "PHY": 1,
            "CHE": 1,
            "ACC": 1,
            "ECO": 1,
            "MATH": 1,
            "A.M": 1,
            "BIO": 1,
            "BS": 1,
            "CS": 2,
            "ENTRE": 2,
            "PSY": 2
        }

        candidates: List[Dict[str, Any]] = []
        for stud in all_students:
            matched_subs = []
            if session_subject_ids:
                matched_subs = [
                    s for s in stud.enrolled_subjects 
                    if s.id.lower() in session_subject_ids or s.code.upper() in session_subject_codes
                ]
            else:
                matched_subs = list(stud.enrolled_subjects)

            if matched_subs:
                matched_subs.sort(key=lambda s: subject_priority.get(s.code.upper(), 99))
                candidates.append({
                    "student": stud,
                    "subject": matched_subs[0]
                })

"""

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('app/allocation_service.py', 'w') as f:
    f.write(new_content)

print("Backend patched 4")
