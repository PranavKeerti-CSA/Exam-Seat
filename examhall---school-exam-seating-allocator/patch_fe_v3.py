import re

with open('src/utils/allocationEngine.ts', 'r') as f:
    content = f.read()

start_marker = "  // Create pools sorted by size descending"
end_marker = "    // Build distributions"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    exit(1)

new_logic = """  // Create pools sorted by size descending
  const pools = Array.from(groupMap.entries()).map(([key, list]) => ({
    key,
    list: [...list],
    subject: list[0]?.subject,
    grade: list[0]?.student.grade,
    originalCount: list.length
  }));
  pools.sort((a, b) => b.list.length - a.list.length);

  class PoolManager {
    pools: any[];
    stream1: any;
    stream2: any;

    constructor(poolsList: any[]) {
      this.pools = poolsList;
      this.stream1 = this._getNextPool(null);
      this.stream2 = this._getNextPool(this.stream1 ? this.stream1.subject.code : null);
    }

    _getNextPool(avoidSubject: string | null) {
      if (this.pools.length === 0) return null;
      if (avoidSubject) {
        const idx = this.pools.findIndex(p => p.subject.code !== avoidSubject);
        if (idx !== -1) {
          return this.pools.splice(idx, 1)[0];
        }
      }
      return this.pools.shift();
    }

    getStudent(streamIdx: number) {
      let pool = streamIdx === 1 ? this.stream1 : this.stream2;
      const otherPool = streamIdx === 1 ? this.stream2 : this.stream1;

      if (pool && pool.list.length > 0) {
        return pool.list.shift();
      }

      const avoidSub = otherPool ? otherPool.subject.code : null;
      const newPool = this._getNextPool(avoidSub);

      if (newPool) {
        if (streamIdx === 1) {
          this.stream1 = newPool;
          pool = this.stream1;
        } else {
          this.stream2 = newPool;
          pool = this.stream2;
        }
        return pool.list.shift();
      }

      if (otherPool && otherPool.list.length > 0) {
        return otherPool.list.shift();
      }

      return null;
    }

    hasStudents() {
      if (this.stream1 && this.stream1.list.length > 0) return true;
      if (this.stream2 && this.stream2.list.length > 0) return true;
      return this.pools.length > 0;
    }
  }

  const pm = new PoolManager(pools);
  const roomAllocations: RoomAllocation[] = [];
  const unassignedStudents: { student: Student; subject: ExamSubject; reason: string }[] = [];
  const conflicts: ConflictWarning[] = [];

  // 3. Allocate Room by Room
  for (const room of activeRooms) {
    if (!pm.hasStudents()) break;

    const rows = room.rows || Math.max(1, Math.ceil(room.capacity / (room.cols || 6)));
    const cols = room.cols || Math.max(1, Math.ceil(room.capacity / rows));
    const capacity = room.capacity;

    const assignedSeats: SeatAssignment[] = [];
    const grid: any[][] = Array(rows).fill(null).map(() => Array(cols).fill(null));
    
    // Step 1: Assign students physically column by column
    let seatsFilled = 0;
    for (let c = 0; c < cols; c++) {
      const streamIdx = c % 2 === 0 ? 1 : 2;
      for (let r = 0; r < rows; r++) {
        if (seatsFilled >= capacity) break;

        const item = pm.getStudent(streamIdx);
        if (item) {
          grid[r][c] = item;
          seatsFilled++;
        }
      }
    }

    // Step 2: Read out in row-major order so the DOM Grid renders it perfectly aligned
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const seatIdx = r * cols + c;
        if (seatIdx >= capacity) break; // Out of bounds for this room

        const seatLabel = `${String.fromCharCode(65 + r)}${c + 1}`;
        const item = grid[r][c];

        if (item) {
          let hasNeighborConflict = false;
          const neighbors = [[r - 1, c], [r + 1, c], [r, c - 1], [r, c + 1]];
          for (const [nr, nc] of neighbors) {
            if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
              const nItem = grid[nr][nc];
              if (nItem && nItem.subject.code === item.subject.code) {
                hasNeighborConflict = true;
                break;
              }
            }
          }

          if (hasNeighborConflict) {
            conflicts.push({
              type: 'neighbor_same_subject',
              severity: 'warning',
              message: `Student ${item.student.rollNo} sitting adjacent to another student with same subject`,
              roomId: room.id,
              studentId: item.student.id,
              seatLabel
            });
          }

          assignedSeats.push({
            seatIndex: seatIdx,
            row: r,
            col: c,
            seatLabel,
            studentId: item.student.id,
            studentRollNo: item.student.rollNo,
            studentName: item.student.name,
            studentGrade: item.student.grade,
            subjectCode: item.subject.code,
            subjectName: item.subject.name,
            subjectColor: item.subject.color,
            isSpecialNeeds: item.student.specialNeeds,
            hasNeighborConflict
          });
        } else {
          assignedSeats.push({
            seatIndex: seatIdx,
            row: r,
            col: c,
            seatLabel
          });
        }
      }
    }

"""

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('src/utils/allocationEngine.ts', 'w') as f:
    f.write(new_content)

print("Frontend patched 3")
