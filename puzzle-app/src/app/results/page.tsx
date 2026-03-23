"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePuzzleStore } from "@/store/usePuzzleStore";
import ResultsSummary from "@/components/ResultsSummary";

export default function ResultsPage() {
  const reset = usePuzzleStore((s) => s.reset);
  const router = useRouter();

  function handlePlayAgain() {
    reset();
    router.push("/");
  }

  return (
    <div className="flex flex-col gap-6">
      <ResultsSummary />
      <button
        onClick={handlePlayAgain}
        className="w-full bg-indigo-600 text-white py-3 rounded-xl font-semibold text-lg hover:bg-indigo-700 transition-colors"
      >
        Play Again
      </button>
    </div>
  );
}
