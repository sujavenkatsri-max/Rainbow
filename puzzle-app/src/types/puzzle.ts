export type QuestionType = "multiple-choice" | "text-input";

export interface Puzzle {
  id: number;
  type: QuestionType;
  question: string;
  options?: string[];
  answer: string;
  explanation?: string;
}

export interface UserAnswer {
  puzzleId: number;
  given: string;
  correct: boolean;
}
