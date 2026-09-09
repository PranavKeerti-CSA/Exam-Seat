import re

with open('app/allocation_service.py', 'r') as f:
    content = f.read()

start_marker = "        # Create pools sorted by size descending"
end_marker = "            room_alloc = schemas.RoomAllocation("

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found")
    exit(1)

new_logic = """        # Create pools sorted by size descending
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

"""

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('app/allocation_service.py', 'w') as f:
    f.write(new_content)

print("Backend patched 3")
