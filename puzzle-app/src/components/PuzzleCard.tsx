"use client";
import { useState } from "react";
import { Puzzle } from "@/types/puzzle";
import { checkAnswer } from "@/lib/scoring";
import { usePuzzleStore } from "@/store/usePuzzleStore";
import MultipleChoiceQuestion from "./MultipleChoiceQuestion";
import TextInputQuestion from "./TextInputQuestion";
import clsx from "clsx";

interface PuzzleCardProps {
  puzzle: Puzzle;
  onNext: () => void;
  isLast: boolean;
}

export default function PuzzleCard({ puzzle, onNext, isLast }: PuzzleCardProps) {
  const [selected, setSelected] = useState<string>("");
  const [submitted, setSubmitted] = useState(false);
  const [correct, setCorrect] = useState(false);
  const submitAnswer = usePuzzleStore((s) => s.submitAnswer);

  function handleSubmit() {
    if (!selected) return;
    const isCorrect = checkAnswer(puzzle, selected);
    setCorrect(isCorrect);
    setSubmitted(true);
    submitAnswer(puzzle.id, selected, isCorrect);
  }

  return (
    <div className="bg-white rounded-2xl shadow-md p-8 flex flex-col gap-6">
      <h2 className="text-xl font-semibold text-gray-800">{puzzle.question}</h2>

      {puzzle.type === "multiple-choice" ? (
        <MultipleChoiceQuestion
          options={puzzle.options!}
          selected={selected}
          submitted={submitted}
          correctAnswer={puzzle.answer}
          onSelect={setSelected}
        />
      ) : (
        <TextInputQuestion
          value={selected}
          submitted={submitted}
          correct={correct}
          onChange={setSelected}
        />
      )}

      {submitted && (
        <div
          className={clsx(
            "rounded-xl px-4 py-3 text-sm font-medium",
            correct ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
          )}
        >
          {correct ? "Correct!" : `Wrong — the answer is: ${puzzle.answer}`}
          {puzzle.explanation && (
            <p className="mt-1 font-normal opacity-80">{puzzle.explanation}</p>
          )}
        </div>
      )}

      <div className="flex justify-end gap-3">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={!selected}
            className="bg-indigo-600 text-white px-6 py-2 rounded-xl font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors"
          >
            Submit
          </button>
        ) : (
          <button
            onClick={onNext}
            className="bg-indigo-600 text-white px-6 py-2 rounded-xl font-semibold hover:bg-indigo-700 transition-colors"
          >
            {isLast ? "See Results" : "Next →"}
          </button>
        )}
      </div>
    </div>
  );
}
