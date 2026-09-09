with open('src/components/AllocationSummaryStats.tsx', 'w') as f:
    f.write("""import React from 'react';
import { SeatingPlan } from '../types';

interface AllocationSummaryStatsProps {
  plan: SeatingPlan | null;
  onOpenSettings: () => void;
  onSelectRoomFilter?: (roomId: string) => void;
  onSortOutConflicts?: () => void;
}

export const AllocationSummaryStats: React.FC<AllocationSummaryStatsProps> = () => {
  return null;
};
""")

print("Stats banner replaced")
