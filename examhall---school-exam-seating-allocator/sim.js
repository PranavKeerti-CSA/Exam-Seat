const pools = [
  { grade: 'XI - B', count: 34 },
  { grade: 'XI - C', count: 34 },
  { grade: 'XI - H', count: 33 },
  { grade: 'XI - G', count: 32 },
  { grade: 'XI - A', count: 30 },
  { grade: 'XI - E', count: 30 },
  { grade: 'XI - D', count: 28 },
  { grade: 'XI - F', count: 25 },
].map(p => {
  const list = [];
  for (let i=0; i<p.count; i++) {
    list.push({
      student: { id: p.grade + i, grade: p.grade },
      subject: { code: 'ENG' }
    });
  }
  return { subject: list[0].subject, grade: p.grade, list };
});

const rooms = [
  { name: 'XI-A', cap: 30, r: 5, c: 6 },
  { name: 'XI-B', cap: 36, r: 6, c: 6 },
  { name: 'XI-C', cap: 36, r: 6, c: 6 },
  { name: 'XI-D', cap: 30, r: 5, c: 6 },
  { name: 'XI-E', cap: 36, r: 6, c: 6 },
];

for (const room of rooms) {
  const assignedSeats = [];
  for (let r=0; r<room.r; r++) {
    for (let c=0; c<room.c; c++) {
      assignedSeats.push({ row: r, col: c });
    }
  }

  let orderedSeats = [];
  for (let c = 0; c < room.c; c++) {
    for (let r = 0; r < room.r; r++) {
      const seat = assignedSeats.find(s => s.row === r && s.col === c);
      if (seat) orderedSeats.push(seat);
    }
  }

  for (const seat of orderedSeats) {
    const activePools = pools.filter(p => p.list.length > 0);
    if (activePools.length === 0) break;

    const leftSeat = assignedSeats.find(s => s.row === seat.row && s.col === seat.col - 1 && s.studentId);
    const topSeat = assignedSeats.find(s => s.row === seat.row - 1 && s.col === seat.col && s.studentId);

    for (const pool of activePools) {
      let score = 0;
      if (topSeat) {
        if (pool.subject.code === topSeat.subjectCode) score += 100;
        if (pool.grade === topSeat.studentGrade) score += 50;
      }
      if (leftSeat) {
        if (pool.subject.code !== leftSeat.subjectCode) score += 50;
        if (pool.grade !== leftSeat.studentGrade) score += 20;
      }
      pool._tempScore = score;
    }

    activePools.sort((a, b) => {
      if (a._tempScore !== b._tempScore) return b._tempScore - a._tempScore;
      return b.list.length - a.list.length;
    });

    const bestPool = activePools[0];
    const cand = bestPool.list.shift();

    seat.studentId = cand.student.id;
    seat.studentGrade = cand.student.grade;
    seat.subjectCode = cand.subject.code;
  }

  const dist = {};
  for (const s of assignedSeats) {
    if (s.studentGrade) {
      dist[s.studentGrade] = (dist[s.studentGrade] || 0) + 1;
    }
  }
  console.log(`Room ${room.name}:`, dist);
}
