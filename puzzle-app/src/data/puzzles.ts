import { Puzzle } from "@/types/puzzle";

export const puzzles: Puzzle[] = [
  {
    id: 0,
    type: "multiple-choice",
    question: "Which planet is closest to the Sun?",
    options: ["Venus", "Mercury", "Mars", "Earth"],
    answer: "mercury",
    explanation: "Mercury is the first planet in our solar system.",
  },
  {
    id: 1,
    type: "text-input",
    question: "What is the only even prime number?",
    answer: "2",
    explanation: "2 is the only even number that is also prime.",
  },
  {
    id: 2,
    type: "multiple-choice",
    question: "What does HTML stand for?",
    options: [
      "Hyper Text Markup Language",
      "High Tech Modern Language",
      "Hyper Transfer Markup Logic",
      "Home Tool Markup Language",
    ],
    answer: "hyper text markup language",
    explanation: "HTML is the standard markup language for web pages.",
  },
  {
    id: 3,
    type: "text-input",
    question: "What keyword is used to define a function in Python?",
    answer: "def",
    explanation: "In Python, functions are defined using the 'def' keyword.",
  },
  {
    id: 4,
    type: "multiple-choice",
    question: "Which data structure uses LIFO (Last In, First Out)?",
    options: ["Queue", "Stack", "Linked List", "Tree"],
    answer: "stack",
    explanation: "A Stack uses LIFO — the last element added is the first removed.",
  },
  {
    id: 5,
    type: "text-input",
    question: "What is 12 × 12?",
    answer: "144",
    explanation: "12 multiplied by 12 equals 144.",
  },
  {
    id: 6,
    type: "multiple-choice",
    question: "Which language is known as the 'language of the web'?",
    options: ["Python", "Java", "JavaScript", "C++"],
    answer: "javascript",
    explanation: "JavaScript runs natively in browsers and powers the modern web.",
  },
  {
    id: 7,
    type: "text-input",
    question: "What is the capital of France?",
    answer: "paris",
    explanation: "Paris is the capital and largest city of France.",
  },
];
