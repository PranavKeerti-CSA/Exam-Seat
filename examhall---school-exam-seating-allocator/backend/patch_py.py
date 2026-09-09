import re

with open('app/allocation_service.py', 'r') as f:
    content = f.read()

start_marker = "            # Choose up to 2 major pools for 50/50 anti-cheating splitting in this room"
end_marker = "            room_alloc = schemas.RoomAllocation("

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    exit(1)

new_logic = """            # We will assign seats one by one, picking the best pool for each seat based on adjacency rules.
            ordered_seats = []
            
            # Generate all seats
            all_seats = []
            for r in range(rows):
                for c in range(cols):
                    if len(all_seats) < capacity:
                        all_seats.append({"row": r, "col": c})
                        
            if options.strategy == 'column_alternate':
                for c in range(cols):
                    for r in range(rows):
                        s = next((seat for seat in all_seats if seat["row"] == r and seat["col"] == c), None)
                        if s:
                            ordered_seats.append(s)
            else:
                ordered_seats = all_seats

            grade_dist = {}
            subject_dist = {}
            total_assigned_room = 0

            for seat in ordered_seats:
                r = seat["row"]
                c = seat["col"]
                seat_idx = r * cols + c
                seat_label = f"{chr(65 + c)}{r + 1}"
                
                active_pools = [p for p in pools if len(p["list"]) > 0]
                if not active_pools:
                    # Empty seat
                    assigned_seats.append(schemas.SeatAssignment(
                        seatIndex=seat_idx,
                        row=r,
                        col=c,
                        seatLabel=seat_label
                    ))
                    continue

                left_seat = grid[r][c-1] if c > 0 else None
                top_seat = grid[r-1][c] if r > 0 else None

                for pool in active_pools:
                    score = 0
                    if options.strategy == 'column_alternate':
                        if top_seat:
                            if pool["subject"].code == top_seat["subject"].code: score += 100
                            if pool["grade"] == top_seat["student"].grade: score += 50
                        if left_seat:
                            if pool["subject"].code != left_seat["subject"].code: score += 50
                            if pool["grade"] != left_seat["student"].grade: score += 20
                    else:
                        if top_seat:
                            if pool["subject"].code != top_seat["subject"].code: score += 50
                            if pool["grade"] != top_seat["student"].grade: score += 20
                        if left_seat:
                            if pool["subject"].code != left_seat["subject"].code: score += 50
                            if pool["grade"] != left_seat["student"].grade: score += 20
                    pool["_tempScore"] = score

                active_pools.sort(key=lambda p: (p["_tempScore"], len(p["list"])), reverse=True)
                
                best_pool = active_pools[0]
                item = best_pool["list"].pop(0)
                
                grid[r][c] = item
                
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

"""

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('app/allocation_service.py', 'w') as f:
    f.write(new_content)

print("Backend patched")
