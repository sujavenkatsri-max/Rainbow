"use client";
import { useParams, useRouter } from "next/navigation";
import { puzzles } from "@/data/puzzles";
import PuzzleCard from "@/components/PuzzleCard";
import ProgressBar from "@/components/ProgressBar";

export default function PuzzlePage() {
  const { id } = useParams();
  const router = useRouter();
  const index = Number(id);
  const puzzle = puzzles[index];

  if (!puzzle) {
    router.replace("/");
    return null;
  }

  function handleNext() {
    if (index + 1 < puzzles.length) {
      router.push(`/puzzle/${index + 1}`);
    } else {
      router.push("/results");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>Question {index + 1} of {puzzles.length}</span>
      </div>
      <ProgressBar current={index + 1} total={puzzles.length} />
      <PuzzleCard puzzle={puzzle} onNext={handleNext} isLast={index === puzzles.length - 1} />
    </div>
  );
}
