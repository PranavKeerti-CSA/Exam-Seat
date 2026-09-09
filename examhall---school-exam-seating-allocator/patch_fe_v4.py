import re

with open('src/utils/allocationEngine.ts', 'r') as f:
    content = f.read()

start_marker = "    if (sessionSubIds.size === 0) {"
end_marker = "    if (chosenSub) {"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    exit(1)

new_logic = """    if (sessionSubIds.size === 0) {
      // General session: student takes first enrolled subject or default
      chosenSub = studentSubs[0] || allSubjects[0] || {
        id: 'sub-gen',
        name: 'General Examination',
        code: 'GEN',
        gradeLevel: student.grade || 'General',
        color: '#2563EB'
      };
    } else {
      const subjectPriority: Record<string, number> = {
        "ENG": 1, "PHY": 1, "CHE": 1, "ACC": 1, "ECO": 1, "MATH": 1, "A.M": 1, "BIO": 1, "BS": 1,
        "CS": 2, "ENTRE": 2, "PSY": 2
      };
      
      const sessionMatchedSubs = studentSubs.filter(s => 
        sessionSubIds.has(s.id.toLowerCase()) || sessionSubCodes.has(s.code.toUpperCase())
      );
      
      if (sessionMatchedSubs.length > 0) {
        sessionMatchedSubs.sort((a, b) => {
          const pA = subjectPriority[a.code.toUpperCase()] || 99;
          const pB = subjectPriority[b.code.toUpperCase()] || 99;
          return pA - pB;
        });
        chosenSub = sessionMatchedSubs[0];
      }
    }

"""

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('src/utils/allocationEngine.ts', 'w') as f:
    f.write(new_content)

print("Frontend patched 4")
