import Link from "next/link";
import { puzzles } from "@/data/puzzles";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center gap-6">
      <div className="bg-white rounded-2xl shadow-md p-10 max-w-md w-full">
        <h2 className="text-3xl font-bold text-gray-800">Welcome to Puzzle Quiz!</h2>
        <p className="text-gray-500 mt-3 text-lg">
          {puzzles.length} puzzles — multiple choice & text input.
        </p>
        <p className="text-gray-400 mt-1 text-sm">Test your knowledge across science, math & tech.</p>
        <Link
          href="/puzzle/0"
          className="mt-8 inline-block bg-indigo-600 text-white px-8 py-3 rounded-xl font-semibold text-lg hover:bg-indigo-700 transition-colors"
        >
          Start Quiz →
        </Link>
      </div>
    </div>
  );
}
