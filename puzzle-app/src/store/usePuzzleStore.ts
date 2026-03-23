import { create } from "zustand";
import { UserAnswer } from "@/types/puzzle";

interface PuzzleStore {
  answers: UserAnswer[];
  score: number;
  submitAnswer: (puzzleId: number, given: string, correct: boolean) => void;
  reset: () => void;
}

export const usePuzzleStore = create<PuzzleStore>((set) => ({
  answers: [],
  score: 0,
  submitAnswer: (puzzleId, given, correct) =>
    set((state) => ({
      answers: [...state.answers, { puzzleId, given, correct }],
      score: correct ? state.score + 1 : state.score,
    })),
  reset: () => set({ answers: [], score: 0 }),
}));
