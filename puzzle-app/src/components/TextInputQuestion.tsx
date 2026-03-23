import clsx from "clsx";

interface TextInputQuestionProps {
  value: string;
  submitted: boolean;
  correct: boolean;
  onChange: (val: string) => void;
}

export default function TextInputQuestion({
  value,
  submitted,
  correct,
  onChange,
}: TextInputQuestionProps) {
  return (
    <input
      type="text"
      value={value}
      disabled={submitted}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Type your answer..."
      className={clsx(
        "w-full px-4 py-3 rounded-xl border-2 text-lg outline-none transition-all",
        !submitted && "border-gray-300 focus:border-indigo-500",
        submitted && correct && "border-green-500 bg-green-50 text-green-800",
        submitted && !correct && "border-red-500 bg-red-50 text-red-800"
      )}
    />
  );
}
