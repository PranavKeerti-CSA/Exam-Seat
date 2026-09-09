import datetime
import math
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app import models, schemas

class AllocationEngine:
    @staticmethod
    def generate_seating_plan(
        session_id: str,
        options: schemas.AllocationOptions,
        db: Session
    ) -> schemas.SeatingPlan:
        exam_session = db.query(models.ExamSession).filter(models.ExamSession.id == session_id).first()
        if not exam_session:
            raise ValueError(f"Exam session {session_id} not found")

        active_rooms = db.query(models.ExamRoom).filter(
            models.ExamRoom.is_active == True,
            models.ExamRoom.capacity > 0
        ).all()

        session_subject_ids = {s.id.lower() for s in exam_session.subjects}
        session_subject_codes = {s.code.upper() for s in exam_session.subjects}
        all_students = db.query(models.Student).all()
        all_subjects_map = {s.id: s for s in db.query(models.Subject).all()}

        # 1. Identify all eligible candidates taking subjects in this session
        
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

        # Resilient fallback: if no candidate matched the session filter, seat all students
        if not candidates and all_students:
            for stud in all_students:
                chosen = stud.enrolled_subjects[0] if stud.enrolled_subjects else (list(all_subjects_map.values())[0] if all_subjects_map else None)
                if chosen:
                    candidates.append({
                        "student": stud,
                        "subject": chosen
                    })

        # 2. Group candidates by Subject Code & Grade
        group_map: Dict[str, List[Dict[str, Any]]] = {}
        for c in candidates:
            key = f"{c['subject'].code}_{c['student'].grade}"
            if key not in group_map:
                group_map[key] = []
            group_map[key].append(c)

        # Sort within each group (special needs first if prioritized, then roll number)
        for key, members in group_map.items():
            members.sort(
                key=lambda x: (
                    0 if (options.prioritizeSpecialNeedsFront and x["student"].special_needs) else 1,
                    x["student"].roll_no
                )
            )

        # Create pools sorted by size descending
        pools = []
        for key, members in group_map.items():
            pools.append({
                "key": key,
                "list": list(members),
                "subject": members[0]["subject"],
                "grade": members[0]["student"].grade,
                "originalCount": len(members)
            })
        pools.sort(key=lambda p: len(p["list"]), reverse=True)

        class PoolManager:
            def __init__(self, pools_list):
                self.pools = pools_list
                self.stream1 = self._get_next_pool(None)
                self.stream2 = self._get_next_pool(self.stream1["subject"].code if self.stream1 else None)
                
            def _get_next_pool(self, avoid_subject):
                if not self.pools:
                    return None
                if avoid_subject:
                    for i, p in enumerate(self.pools):
                        if p["subject"].code != avoid_subject:
                            return self.pools.pop(i)
                return self.pools.pop(0)

            def get_student(self, stream_idx):
                pool = self.stream1 if stream_idx == 1 else self.stream2
                other_pool = self.stream2 if stream_idx == 1 else self.stream1
                
                if pool and len(pool["list"]) > 0:
                    return pool["list"].pop(0)
                    
                avoid_sub = other_pool["subject"].code if other_pool else None
                new_pool = self._get_next_pool(avoid_sub)
                
                if new_pool:
                    if stream_idx == 1:
                        self.stream1 = new_pool
                        pool = self.stream1
                    else:
                        self.stream2 = new_pool
                        pool = self.stream2
                    return pool["list"].pop(0)
                    
                if other_pool and len(other_pool["list"]) > 0:
                    return other_pool["list"].pop(0)
                    
                return None

            def has_students(self):
                if self.stream1 and len(self.stream1["list"]) > 0: return True
                if self.stream2 and len(self.stream2["list"]) > 0: return True
                return len(self.pools) > 0

        pm = PoolManager(pools)
        room_allocations: List[schemas.RoomAllocation] = []
        unassigned_students: List[schemas.UnassignedStudent] = []
        conflicts: List[schemas.ConflictWarning] = []

        db.query(models.SeatAllocation).filter(models.SeatAllocation.session_id == session_id).delete()

        # 3. Allocate Room by Room
        for room in active_rooms:
            if not pm.has_students():
                break

            rows = room.rows or max(1, math.ceil(room.capacity / (room.cols or 6)))
            cols = room.cols or max(1, math.ceil(room.capacity / rows))
            capacity = room.capacity

            grid: List[List[Optional[Dict[str, Any]]]] = [[None for _ in range(cols)] for _ in range(rows)]
            
            # Step 1: Assign students column by column physically
            seats_filled = 0
            for c in range(cols):
                stream_idx = 1 if c % 2 == 0 else 2
                for r in range(rows):
                    if seats_filled >= capacity:
                        break
                    
                    item = pm.get_student(stream_idx)
                    if item:
                        grid[r][c] = item
                        seats_filled += 1
                        
            # Step 2: Read grid row by row to match the CSS Grid DOM rendering
            assigned_seats: List[schemas.SeatAssignment] = []
            grade_dist = {}
            subject_dist = {}
            total_assigned_room = 0
            
            for r in range(rows):
                for c in range(cols):
                    # In CSS grid, index = r * cols + c. This maps perfectly to row-major flattening.
                    seat_idx = r * cols + c
                    
                    # Coordinate system: A1, B1, C1 are in the first column. 
                    # So letter corresponds to ROW, number corresponds to COLUMN.
                    seat_label = f"{chr(65 + r)}{c + 1}"
                    
                    # If this physical space exceeds the room's odd capacity, treat as wall/empty
                    if seat_idx >= capacity:
                        break
                        
                    item = grid[r][c]
                    
                    if item:
                        total_assigned_room += 1
                        grd = item["student"].grade
                        sub_code = item["subject"].code
                        grade_dist[grd] = grade_dist.get(grd, 0) + 1
                        subject_dist[sub_code] = subject_dist.get(sub_code, 0) + 1

                        has_neighbor_conflict = False
                        neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
                        for nr, nc in neighbors:
                            if 0 <= nr < rows and 0 <= nc < cols:
                                n_item = grid[nr][nc]
                                if n_item and n_item["subject"].code == sub_code:
                                    has_neighbor_conflict = True
                                    break

                        if has_neighbor_conflict:
                            conflicts.append(schemas.ConflictWarning(
                                type="neighbor_same_subject",
                                severity="warning",
                                message=f"Student {item['student'].roll_no} sitting adjacent to another student with same subject {sub_code}",
                                roomId=room.id,
                                studentId=item["student"].id,
                                seatLabel=seat_label
                            ))

                        seat_assign = schemas.SeatAssignment(
                            seatIndex=seat_idx,
                            row=r,
                            col=c,
                            seatLabel=seat_label,
                            studentId=item["student"].id,
                            studentRollNo=item["student"].roll_no,
                            studentName=item["student"].name,
                            studentGrade=item["student"].grade,
                            subjectCode=item["subject"].code,
                            subjectName=item["subject"].name,
                            subjectColor=item["subject"].color,
                            isSpecialNeeds=item["student"].special_needs,
                            hasNeighborConflict=has_neighbor_conflict
                        )
                        assigned_seats.append(seat_assign)

                        db_alloc = models.SeatAllocation(
                            id=f"alloc-{session_id}-{room.id}-{seat_idx}",
                            session_id=session_id,
                            room_id=room.id,
                            seat_index=seat_idx,
                            row=r,
                            col=c,
                            seat_label=seat_label,
                            student_id=item["student"].id,
                            subject_id=item["subject"].id,
                            neighbor_conflict=has_neighbor_conflict,
                            is_special_needs=item["student"].special_needs
                        )
                        db.add(db_alloc)

                        existing_mon = db.query(models.StudentMonitoring).filter(
                            models.StudentMonitoring.student_id == item["student"].id,
                            models.StudentMonitoring.session_id == session_id
                        ).first()

                        if existing_mon:
                            existing_mon.room_id = room.id
                            existing_mon.seat_label = seat_label
                        else:
                            new_mon = models.StudentMonitoring(
                                id=f"mon-{session_id}-{item['student'].id}",
                                student_id=item["student"].id,
                                session_id=session_id,
                                room_id=room.id,
                                seat_label=seat_label,
                                status="not_checked_in"
                            )
                            db.add(new_mon)
                    else:
                        assigned_seats.append(schemas.SeatAssignment(
                            seatIndex=seat_idx,
                            row=r,
                            col=c,
                            seatLabel=seat_label
                        ))

            room_alloc = schemas.RoomAllocation(
                roomId=room.id,
                roomName=room.name,
                building=room.building or "",
                floor=room.floor or "",
                capacity=room.capacity,
                rows=rows,
                cols=cols,
                benchType=room.bench_type,
                assignedSeats=assigned_seats,
                totalAssigned=total_assigned_room,
                gradeDistribution=grade_dist,
                subjectDistribution=subject_dist,
                invigilator="Allocated"
            )
            room_allocations.append(room_alloc)

        # Record any unassigned students
        for p in pools:
            for item in p["list"]:
                unassigned_students.append(schemas.UnassignedStudent(
                    student=schemas.Student(
                        id=item["student"].id,
                        rollNo=item["student"].roll_no,
                        name=item["student"].name,
                        grade=item["student"].grade,
                        gender=item["student"].gender,
                        specialNeeds=item["student"].special_needs,
                        enrolledSubjectIds=[s.id for s in item["student"].enrolled_subjects]
                    ),
                    subject=schemas.ExamSubject(
                        id=item["subject"].id,
                        code=item["subject"].code,
                        name=item["subject"].name,
                        gradeLevel=item["subject"].grade_level,
                        color=item["subject"].color
                    ),
                    reason="Exam hall capacity exhausted"
                ))

        # Compute global stats
        total_candidates = len(candidates)
        total_assigned = sum(r.totalAssigned for r in room_allocations)
        total_cap_avail = sum(r.capacity for r in active_rooms)
        rooms_used = sum(1 for r in room_allocations if r.totalAssigned > 0)
        mixed_rooms = sum(1 for r in room_allocations if len(r.subjectDistribution) > 1)
        single_rooms = sum(1 for r in room_allocations if len(r.subjectDistribution) == 1)

        conflict_count = len([c for c in conflicts if c.severity in ["warning", "error"]])
        cheat_prev_index = 100.0
        if total_assigned > 0:
            seated_conflicts = sum(
                1 for r in room_allocations for s in r.assignedSeats if s.studentId and s.hasNeighborConflict
            )
            cheat_prev_index = max(0.0, round(100.0 * (1 - (seated_conflicts / total_assigned)), 1))

        stats = schemas.SeatingPlanStats(
            totalStudents=total_candidates,
            totalAssigned=total_assigned,
            totalRoomsUsed=rooms_used,
            totalCapacityAvailable=total_cap_avail,
            overallUtilizationPercent=round(100.0 * total_assigned / max(1, total_cap_avail), 1),
            mixedRoomCount=mixed_rooms,
            singleGroupRoomCount=single_rooms,
            conflictCount=conflict_count,
            cheatPreventionIndex=cheat_prev_index
        )

        db.commit()

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return schemas.SeatingPlan(
            id=f"plan-{session_id}-{int(now_utc.timestamp())}",
            sessionId=exam_session.id,
            sessionName=exam_session.name,
            sessionDate=exam_session.date,
            sessionTime=exam_session.time_slot,
            createdAt=now_utc.isoformat(),
            options=options,
            roomAllocations=room_allocations,
            unassignedStudents=unassigned_students,
            conflicts=conflicts,
            stats=stats
        )
