"use client";
import { usePuzzleStore } from "@/store/usePuzzleStore";
import { puzzles } from "@/data/puzzles";

export default function ScoreBadge() {
  const score = usePuzzleStore((s) => s.score);
  return (
    <span className="bg-indigo-100 text-indigo-800 font-semibold px-3 py-1 rounded-full text-sm">
      Score: {score} / {puzzles.length}
    </span>
  );
}
