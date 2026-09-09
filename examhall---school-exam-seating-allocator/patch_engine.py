import re

with open('src/utils/allocationEngine.ts', 'r') as f:
    content = f.read()

# Find the start of the block to replace
start_marker = "// Determine how many students from each group to place in this room"
end_marker = "// Build distributions"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found!")
    exit(1)

new_logic = """// We will assign seats one by one, picking the best pool for each seat based on adjacency rules.
    let orderedSeats = [...assignedSeats];
    if (options.strategy === 'column_alternate') {
      orderedSeats = [];
      for (let c = 0; c < cols; c++) {
        for (let r = 0; r < rows; r++) {
          const seat = assignedSeats.find(s => s.row === r && s.col === c);
          if (seat) orderedSeats.push(seat);
        }
      }
    }

    for (const seat of orderedSeats) {
      const activePools = pools.filter(p => p.list.length > 0);
      if (activePools.length === 0) break;

      const leftSeat = assignedSeats.find(s => s.row === seat.row && s.col === seat.col - 1 && s.studentId);
      const topSeat = assignedSeats.find(s => s.row === seat.row - 1 && s.col === seat.col && s.studentId);

      for (const pool of activePools) {
        let score = 0;
        if (options.strategy === 'column_alternate') {
          if (topSeat) {
            if (pool.subject.code === topSeat.subjectCode) score += 100;
            if (pool.grade === topSeat.studentGrade) score += 50;
          }
          if (leftSeat) {
            if (pool.subject.code !== leftSeat.subjectCode) score += 50;
            if (pool.grade !== leftSeat.studentGrade) score += 20;
          }
        } else {
          if (topSeat) {
            if (pool.subject.code !== topSeat.subjectCode) score += 50;
            if (pool.grade !== topSeat.studentGrade) score += 20;
          }
          if (leftSeat) {
            if (pool.subject.code !== leftSeat.subjectCode) score += 50;
            if (pool.grade !== leftSeat.studentGrade) score += 20;
          }
        }
        (pool as any)._tempScore = score;
      }

      activePools.sort((a, b) => {
        const scoreA = (a as any)._tempScore;
        const scoreB = (b as any)._tempScore;
        if (scoreA !== scoreB) return scoreB - scoreA;
        return b.list.length - a.list.length;
      });

      const bestPool = activePools[0];
      const cand = bestPool.list.shift()!;

      seat.studentId = cand.student.id;
      seat.studentRollNo = cand.student.rollNo;
      seat.studentName = cand.student.name;
      seat.studentGrade = cand.student.grade;
      seat.subjectCode = cand.subject.code;
      seat.subjectName = cand.subject.name;
      seat.subjectColor = cand.subject.color;
      seat.isSpecialNeeds = cand.student.specialNeeds;
    }

    """

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('src/utils/allocationEngine.ts', 'w') as f:
    f.write(new_content)

print("Patched successfully!")
