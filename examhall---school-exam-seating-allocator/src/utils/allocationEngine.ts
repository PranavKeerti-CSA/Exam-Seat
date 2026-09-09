import { 
  ExamRoom, 
  ExamSubject, 
  Student, 
  ExamSession, 
  AllocationOptions, 
  SeatingPlan, 
  RoomAllocation, 
  SeatAssignment, 
  ConflictWarning 
} from '../types';

interface StudentToSeat {
  student: Student;
  subject: ExamSubject;
}

export function runSeatingAllocation(
  session: ExamSession,
  allRooms: ExamRoom[],
  allStudents: Student[],
  allSubjects: ExamSubject[],
  options: AllocationOptions
): SeatingPlan {
  // Ensure active rooms
  let activeRooms = allRooms.filter(r => r.isActive && r.capacity > 0);
  if (activeRooms.length === 0 && allRooms.length > 0) {
    activeRooms = allRooms.filter(r => r.capacity > 0);
  }

  // Build lookup maps for subjects by ID and by code
  const subjectById = new Map<string, ExamSubject>(allSubjects.map(s => [s.id.toLowerCase(), s]));
  const subjectByCode = new Map<string, ExamSubject>(allSubjects.map(s => [s.code.toUpperCase(), s]));

  // Find session subject IDs and codes
  const sessionSubIds = new Set((session?.subjectIds || []).map(id => id.toLowerCase()));
  const sessionSubCodes = new Set<string>();
  for (const sId of sessionSubIds) {
    if (subjectById.has(sId)) {
      sessionSubCodes.add(subjectById.get(sId)!.code.toUpperCase());
    } else if (subjectByCode.has(sId.toUpperCase())) {
      sessionSubCodes.add(sId.toUpperCase());
    }
  }

  // 1. Identify all eligible students taking exams in this session
  const candidates: StudentToSeat[] = [];

  for (const student of allStudents) {
    const studentSubs: ExamSubject[] = student.enrolledSubjectIds
      .map(id => subjectById.get(id.toLowerCase()) || subjectByCode.get(id.toUpperCase()))
      .filter((s): s is ExamSubject => Boolean(s));

    let chosenSub: ExamSubject | null = null;

    if (sessionSubIds.size === 0) {
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

    if (chosenSub) {
      candidates.push({
        student,
        subject: chosenSub
      });
    }
  }

  // Fallback: if session specified subjects but none matched, seat all students
  if (candidates.length === 0 && allStudents.length > 0) {
    for (const student of allStudents) {
      const studentSubs = student.enrolledSubjectIds
        .map(id => subjectById.get(id.toLowerCase()) || subjectByCode.get(id.toUpperCase()))
        .filter((s): s is ExamSubject => Boolean(s));
      const fallbackSub = studentSubs[0] || allSubjects[0] || {
        id: 'sub-gen',
        name: 'General Examination',
        code: 'GEN',
        gradeLevel: student.grade || 'General',
        color: '#2563EB'
      };
      candidates.push({
        student,
        subject: fallbackSub
      });
    }
  }

  // 2. Group candidates by Subject / Grade Level
  const groupMap = new Map<string, StudentToSeat[]>();
  for (const c of candidates) {
    const groupKey = `${c.subject.code}_${c.student.grade}`;
    if (!groupMap.has(groupKey)) {
      groupMap.set(groupKey, []);
    }
    groupMap.get(groupKey)!.push(c);
  }

  // Sort candidates inside groups (e.g., special needs first, then roll number order)
  for (const group of groupMap.values()) {
    group.sort((a, b) => {
      if (options.prioritizeSpecialNeedsFront) {
        if (a.student.specialNeeds && !b.student.specialNeeds) return -1;
        if (!a.student.specialNeeds && b.student.specialNeeds) return 1;
      }
      return a.student.rollNo.localeCompare(b.student.rollNo, undefined, { numeric: true });
    });
  }

  // Create pools sorted by size descending
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

    // Build distributions
    const gradeDist: Record<string, number> = {};
    const subDist: Record<string, number> = {};
    let assignedCount = 0;

    for (const seat of assignedSeats) {
      if (seat.studentId) {
        assignedCount++;
        if (seat.studentGrade) {
          gradeDist[seat.studentGrade] = (gradeDist[seat.studentGrade] || 0) + 1;
        }
        if (seat.subjectCode) {
          subDist[seat.subjectCode] = (subDist[seat.subjectCode] || 0) + 1;
        }
      }
    }

    // Evaluate anti-cheating neighbor conflicts in this room
    if (options.avoidAdjacentSameSubject) {
      const seatMatrix: (SeatAssignment | undefined)[][] = Array(rows).fill(null).map(() => Array(cols).fill(undefined));
      for (const seat of assignedSeats) {
        seatMatrix[seat.row][seat.col] = seat;
      }

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const seat = seatMatrix[r][c];
          if (seat && seat.subjectCode) {
            // Check adjacent seats: Left, Right, Front, Back
            const neighbors = [
              seatMatrix[r]?.[c - 1], // Left
              seatMatrix[r]?.[c + 1], // Right
              seatMatrix[r - 1]?.[c], // Front
              seatMatrix[r + 1]?.[c]  // Back
            ];

            const sameSubjectNeighbor = neighbors.find(n => n && n.studentId && n.subjectCode === seat.subjectCode);
            if (sameSubjectNeighbor) {
              seat.hasNeighborConflict = true;
            }
          }
        }
      }
    }

    roomAllocations.push({
      roomId: room.id,
      roomName: room.name,
      building: room.building,
      floor: room.floor,
      capacity: room.capacity,
      rows,
      cols,
      benchType: room.benchType,
      assignedSeats,
      totalAssigned: assignedCount,
      gradeDistribution: gradeDist,
      subjectDistribution: subDist
    });
  }

  // 4. Check for any remaining unassigned students (overflow)
  for (const pool of pools) {
    for (const leftover of pool.list) {
      unassignedStudents.push({
        student: leftover.student,
        subject: leftover.subject,
        reason: 'Classroom capacity exhausted. Add more rooms or activate larger halls.'
      });
      conflicts.push({
        type: 'unassigned',
        severity: 'error',
        message: `Student ${leftover.student.name} (${leftover.student.rollNo}) unallocated for ${leftover.subject.name}`,
        studentId: leftover.student.id
      });
    }
  }

  // 5. Compute global statistics
  const totalAssigned = roomAllocations.reduce((acc, r) => acc + r.totalAssigned, 0);
  const totalCapacityAvailable = activeRooms.reduce((acc, r) => acc + r.capacity, 0);
  const overallUtilizationPercent = totalCapacityAvailable > 0 
    ? Math.round((totalAssigned / totalCapacityAvailable) * 100) 
    : 0;

  const mixedRoomCount = roomAllocations.filter(r => Object.keys(r.gradeDistribution).length > 1).length;
  const singleGroupRoomCount = roomAllocations.filter(r => Object.keys(r.gradeDistribution).length === 1).length;

  let totalNeighborConflicts = 0;
  for (const r of roomAllocations) {
    for (const s of r.assignedSeats) {
      if (s.studentId && s.hasNeighborConflict) {
        totalNeighborConflicts++;
      }
    }
  }

  const cheatPreventionIndex = totalAssigned > 0
    ? Math.max(0, Math.round(((totalAssigned - totalNeighborConflicts) / totalAssigned) * 100))
    : 100;

  return {
    id: `plan-${Date.now()}`,
    sessionId: session.id,
    sessionName: session.name,
    sessionDate: session.date,
    sessionTime: session.timeSlot,
    createdAt: new Date().toISOString(),
    options,
    roomAllocations,
    unassignedStudents,
    conflicts,
    stats: {
      totalStudents: candidates.length,
      totalAssigned,
      totalRoomsUsed: roomAllocations.filter(r => r.totalAssigned > 0).length,
      totalCapacityAvailable,
      overallUtilizationPercent,
      mixedRoomCount,
      singleGroupRoomCount,
      conflictCount: conflicts.length + totalNeighborConflicts,
      cheatPreventionIndex
    }
  };
}

export function resolveConflicts(plan: SeatingPlan): SeatingPlan {
  const newPlan: SeatingPlan = JSON.parse(JSON.stringify(plan));
  
  for (const room of newPlan.roomAllocations) {
    const { rows, cols, assignedSeats } = room;
    
    let madeChanges = true;
    let iterations = 0;
    while (madeChanges && iterations < 50) {
      madeChanges = false;
      iterations++;
      
      const seatMatrix: (SeatAssignment | undefined)[][] = Array(rows).fill(null).map(() => Array(cols).fill(undefined));
      for (const seat of assignedSeats) {
        seatMatrix[seat.row][seat.col] = seat;
        seat.hasNeighborConflict = false;
      }

      const conflictSeats: SeatAssignment[] = [];

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const seat = seatMatrix[r][c];
          if (seat && seat.subjectCode) {
            const neighbors = [
              seatMatrix[r]?.[c - 1], // Left
              seatMatrix[r]?.[c + 1], // Right
              seatMatrix[r - 1]?.[c], // Front
              seatMatrix[r + 1]?.[c]  // Back
            ];

            const sameSubjectNeighbor = neighbors.find(n => n && n.studentId && n.subjectCode === seat.subjectCode);
            if (sameSubjectNeighbor) {
              seat.hasNeighborConflict = true;
              if (!conflictSeats.find(s => s.seatIndex === seat.seatIndex)) {
                conflictSeats.push(seat);
              }
            }
          }
        }
      }

      if (conflictSeats.length === 0) break;

      // Swap to resolve: find a seat that is in conflict and swap with another seat of the same subject but different grade
      for (const conflictSeat of conflictSeats) {
        // We want to break the adjacency. If we swap conflictSeat with swapCandidate (same subject, different grade),
        // we might fix it if the classes are interleaved.
        const swapCandidate = assignedSeats.find(s => 
          s.studentId && 
          s.subjectCode === conflictSeat.subjectCode && 
          s.studentGrade !== conflictSeat.studentGrade &&
          s.seatIndex !== conflictSeat.seatIndex
        );

        if (swapCandidate) {
          const temp = {
            studentId: conflictSeat.studentId,
            studentRollNo: conflictSeat.studentRollNo,
            studentName: conflictSeat.studentName,
            studentGrade: conflictSeat.studentGrade,
            subjectCode: conflictSeat.subjectCode,
            subjectName: conflictSeat.subjectName,
            subjectColor: conflictSeat.subjectColor,
            isSpecialNeeds: conflictSeat.isSpecialNeeds
          };

          conflictSeat.studentId = swapCandidate.studentId;
          conflictSeat.studentRollNo = swapCandidate.studentRollNo;
          conflictSeat.studentName = swapCandidate.studentName;
          conflictSeat.studentGrade = swapCandidate.studentGrade;
          conflictSeat.subjectCode = swapCandidate.subjectCode;
          conflictSeat.subjectName = swapCandidate.subjectName;
          conflictSeat.subjectColor = swapCandidate.subjectColor;
          conflictSeat.isSpecialNeeds = swapCandidate.isSpecialNeeds;

          swapCandidate.studentId = temp.studentId;
          swapCandidate.studentRollNo = temp.studentRollNo;
          swapCandidate.studentName = temp.studentName;
          swapCandidate.studentGrade = temp.studentGrade;
          swapCandidate.subjectCode = temp.subjectCode;
          swapCandidate.subjectName = temp.subjectName;
          swapCandidate.subjectColor = temp.subjectColor;
          swapCandidate.isSpecialNeeds = temp.isSpecialNeeds;

          madeChanges = true;
          break;
        }
      }
    }
  }

  // Re-evaluate conflicts for the final plan
  newPlan.conflicts = [];
  let totalNeighborConflicts = 0;
  for (const room of newPlan.roomAllocations) {
    const { rows, cols, assignedSeats } = room;
    const seatMatrix: (SeatAssignment | undefined)[][] = Array(rows).fill(null).map(() => Array(cols).fill(undefined));
    for (const seat of assignedSeats) {
      seatMatrix[seat.row][seat.col] = seat;
      seat.hasNeighborConflict = false;
    }
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const seat = seatMatrix[r][c];
        if (seat && seat.subjectCode) {
          const neighbors = [
            seatMatrix[r]?.[c - 1],
            seatMatrix[r]?.[c + 1],
            seatMatrix[r - 1]?.[c],
            seatMatrix[r + 1]?.[c]
          ];
          const sameSubjectNeighbor = neighbors.find(n => n && n.studentId && n.subjectCode === seat.subjectCode);
          if (sameSubjectNeighbor) {
            seat.hasNeighborConflict = true;
            totalNeighborConflicts++;
          }
        }
      }
    }
  }
  
  if (totalNeighborConflicts > 0) {
    // each pair counts as 2 neighbor conflicts
    for(let i=0; i<Math.ceil(totalNeighborConflicts / 2); i++) {
        newPlan.conflicts.push({
            type: 'neighbor_conflict',
            severity: 'warning',
            message: 'Neighbor proximity detected (same subject)',
            studentId: ''
        });
    }
  }

  // Preserve unassigned students conflicts
  for (const un of newPlan.unassignedStudents) {
    newPlan.conflicts.push({
      type: 'unassigned',
      severity: 'error',
      message: `Student unallocated`,
      studentId: un.student.id
    });
  }

  return newPlan;
}
