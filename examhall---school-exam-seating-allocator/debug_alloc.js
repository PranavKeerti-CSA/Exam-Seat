import fs from 'fs';

const students = [];
const grades = ['XI - B', 'XI - C', 'XI - H', 'XI - G', 'XI - A', 'XI - E', 'XI - D', 'XI - F'];
const counts = [34, 34, 33, 32, 30, 30, 28, 25];
for(let i=0; i<grades.length; i++) {
  for(let j=0; j<counts[i]; j++) {
    students.push({
      id: grades[i] + '_' + j,
      rollNo: grades[i] + '_' + j,
      name: 'Student ' + j,
      grade: grades[i],
      gender: 'M',
      specialNeeds: false,
      enrolledSubjectIds: ['sub-eng']
    });
  }
}

const subjects = [
  { id: 'sub-eng', code: 'ENG', name: 'English', gradeLevel: 'General', color: '#000' }
];

const rooms = [
  { id: 'r1', name: 'XI-A', building: 'B1', floor: '1', capacity: 30, rows: 5, cols: 6, benchType: 'single', isActive: true },
  { id: 'r2', name: 'XI-B', building: 'B1', floor: '1', capacity: 36, rows: 6, cols: 6, benchType: 'single', isActive: true },
  { id: 'r3', name: 'XI-C', building: 'B1', floor: '1', capacity: 36, rows: 6, cols: 6, benchType: 'single', isActive: true },
  { id: 'r4', name: 'XI-D', building: 'B1', floor: '1', capacity: 30, rows: 5, cols: 6, benchType: 'single', isActive: true },
  { id: 'r5', name: 'XI-E', building: 'B1', floor: '1', capacity: 36, rows: 6, cols: 6, benchType: 'single', isActive: true },
];

const session = {
  id: 'sess-1',
  name: 'Eng',
  date: '2023-01-01',
  timeSlot: 'Morning',
  subjectIds: ['sub-eng']
};

const options = {
  strategy: 'column_alternate',
  fillPattern: 'sequential',
  prioritizeSpecialNeedsFront: false,
  avoidSameSubjectAdjacent: true
};

import { runSeatingAllocation } from './src/utils/allocationEngine.ts';

const plan = runSeatingAllocation(session, rooms, students, subjects, options);

for (const r of plan.roomAllocations) {
  console.log(`Room ${r.roomName}:`, r.gradeDistribution);
}
