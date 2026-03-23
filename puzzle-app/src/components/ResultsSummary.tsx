"use client";
import { usePuzzleStore } from "@/store/usePuzzleStore";
import { puzzles } from "@/data/puzzles";
import clsx from "clsx";

export default function ResultsSummary() {
  const { answers, score } = usePuzzleStore();

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-indigo-600 text-white rounded-2xl p-8 text-center">
        <p className="text-lg font-medium opacity-80">Your Score</p>
        <p className="text-6xl font-bold mt-2">{score} / {puzzles.length}</p>
        <p className="mt-3 text-indigo-200">
          {score === puzzles.length
            ? "Perfect score!"
            : score >= puzzles.length / 2
            ? "Well done!"
            : "Keep practicing!"}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {answers.map((ans) => {
          const puzzle = puzzles.find((p) => p.id === ans.puzzleId)!;
          return (
            <div
              key={ans.puzzleId}
              className={clsx(
                "rounded-xl border-2 p-4",
                ans.correct ? "border-green-300 bg-green-50" : "border-red-300 bg-red-50"
              )}
            >
              <p className="font-medium text-gray-800">{puzzle.question}</p>
              <p className="text-sm mt-1">
                Your answer:{" "}
                <span className={clsx("font-semibold", ans.correct ? "text-green-700" : "text-red-700")}>
                  {ans.given}
                </span>
              </p>
              {!ans.correct && (
                <p className="text-sm text-gray-600 mt-0.5">
                  Correct answer: <span className="font-semibold text-green-700">{puzzle.answer}</span>
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
