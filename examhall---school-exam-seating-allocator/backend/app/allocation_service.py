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

        room_allocations: List[schemas.RoomAllocation] = []
        unassigned_students: List[schemas.UnassignedStudent] = []
        conflicts: List[schemas.ConflictWarning] = []

        # Clear existing allocations for this session in DB
        db.query(models.SeatAllocation).filter(models.SeatAllocation.session_id == session_id).delete()

        # 3. Allocate Room by Room
        for room in active_rooms:
            total_remaining = sum(len(p["list"]) for p in pools)
            if total_remaining == 0:
                break

            rows = room.rows or max(1, math.ceil(room.capacity / (room.cols or 6)))
            cols = room.cols or max(1, math.ceil(room.capacity / rows))
            capacity = room.capacity

            # Initialize seat grid
            grid: List[List[Optional[Dict[str, Any]]]] = [[None for _ in range(cols)] for _ in range(rows)]
            assigned_seats: List[schemas.SeatAssignment] = []

            # Choose up to 2 major pools for 50/50 anti-cheating splitting in this room
            available_pools = [p for p in pools if len(p["list"]) > 0]
            if not available_pools:
                break

            primary_pool = available_pools[0]
            secondary_pool = available_pools[1] if len(available_pools) > 1 else None

            # Half capacity each for 50/50 split
            half_cap = math.ceil(capacity / 2)
            primary_budget = min(half_cap, len(primary_pool["list"]))
            secondary_budget = min(capacity - primary_budget, len(secondary_pool["list"])) if secondary_pool else 0

            room_students_to_seat: List[Dict[str, Any]] = []
            
            # Take students from primary pool
            for _ in range(primary_budget):
                if primary_pool["list"]:
                    room_students_to_seat.append(primary_pool["list"].pop(0))

            # Take students from secondary pool
            if secondary_pool and secondary_budget > 0:
                for _ in range(secondary_budget):
                    if secondary_pool["list"]:
                        room_students_to_seat.append(secondary_pool["list"].pop(0))

            # If capacity remains, draw from leftovers
            remaining_cap = capacity - len(room_students_to_seat)
            if remaining_cap > 0:
                for p in pools:
                    while p["list"] and len(room_students_to_seat) < capacity:
                        room_students_to_seat.append(p["list"].pop(0))

            # Separate special needs to put in front row
            front_students = [s for s in room_students_to_seat if s["student"].special_needs]
            regular_students = [s for s in room_students_to_seat if not s["student"].special_needs]

            # Split regular students into 2 alternate streams (by subject or grade)
            primary_code = primary_pool["subject"].code
            pool_a = [s for s in regular_students if s["subject"].code == primary_code]
            pool_b = [s for s in regular_students if s["subject"].code != primary_code]

            # If single subject in room, alternate by section/grade
            if not pool_b and len(regular_students) > 1:
                p_grade = regular_students[0]["student"].grade
                pool_a = [s for s in regular_students if s["student"].grade == p_grade]
                pool_b = [s for s in regular_students if s["student"].grade != p_grade]

            # Place special needs first in front row
            front_idx = 0
            for c in range(cols):
                if front_idx < len(front_students) and c < capacity:
                    grid[0][c] = front_students[front_idx]
                    front_idx += 1

            # Fill remaining seats in alternating checkerboard pattern
            for r in range(rows):
                for c in range(cols):
                    seat_idx = r * cols + c
                    if seat_idx >= capacity:
                        continue
                    if grid[r][c] is not None:
                        continue

                    # Alternate between pool_a and pool_b based on checkerboard parity
                    if (r + c) % 2 == 0:
                        chosen = pool_a.pop(0) if pool_a else (pool_b.pop(0) if pool_b else None)
                    else:
                        chosen = pool_b.pop(0) if pool_b else (pool_a.pop(0) if pool_a else None)

                    grid[r][c] = chosen

            # Check neighbor conflicts and build SeatAssignment objects
            grade_dist: Dict[str, int] = {}
            subject_dist: Dict[str, int] = {}
            total_assigned_room = 0

            for r in range(rows):
                for c in range(cols):
                    seat_idx = r * cols + c
                    if seat_idx >= capacity:
                        continue

                    seat_letter = chr(65 + r) if r < 26 else f"R{r+1}"
                    seat_label = f"{seat_letter}{c + 1}"
                    item = grid[r][c]

                    has_neighbor_conflict = False
                    if item:
                        total_assigned_room += 1
                        sub_code = item["subject"].code
                        grd = item["student"].grade

                        grade_dist[grd] = grade_dist.get(grd, 0) + 1
                        subject_dist[sub_code] = subject_dist.get(sub_code, 0) + 1

                        # Check adjacent cells for identical subject
                        neighbors = [
                            (r - 1, c),  # Top
                            (r + 1, c),  # Bottom
                            (r, c - 1),  # Left
                            (r, c + 1),  # Right
                        ]
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

                        # Insert into DB models.SeatAllocation
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

                        # Update or create StudentMonitoring record for student
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
                        # Empty seat
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
