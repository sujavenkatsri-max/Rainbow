import clsx from "clsx";

interface MultipleChoiceQuestionProps {
  options: string[];
  selected: string | null;
  submitted: boolean;
  correctAnswer: string;
  onSelect: (option: string) => void;
}

export default function MultipleChoiceQuestion({
  options,
  selected,
  submitted,
  correctAnswer,
  onSelect,
}: MultipleChoiceQuestionProps) {
  return (
    <div className="flex flex-col gap-3">
      {options.map((opt) => {
        const isSelected = selected === opt;
        const isCorrect = opt.toLowerCase() === correctAnswer.toLowerCase();
        return (
          <button
            key={opt}
            disabled={submitted}
            onClick={() => onSelect(opt)}
            className={clsx(
              "w-full text-left px-4 py-3 rounded-xl border-2 font-medium transition-all",
              !submitted && "hover:border-indigo-400 hover:bg-indigo-50",
              isSelected && !submitted && "border-indigo-500 bg-indigo-50",
              submitted && isCorrect && "border-green-500 bg-green-50 text-green-800",
              submitted && isSelected && !isCorrect && "border-red-500 bg-red-50 text-red-800",
              !isSelected && !isCorrect && submitted && "border-gray-200 text-gray-400",
              !isSelected && !submitted && "border-gray-200"
            )}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}
