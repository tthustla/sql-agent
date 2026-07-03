"""
CLI entry point.

Usage:
  python src/main.py "Which product category had the most revenue last month?"
  python src/main.py --max-steps 20 "Which product category had the most revenue last month?"
  python src/main.py --log-turns "Which product category had the most revenue last month?"
  python src/main.py          # prompts interactively if no argument given
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow imports from src/ when run from project root
sys.path.insert(0, str(Path(__file__).parent))

from agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="SQL agent over the e-commerce warehouse.")
    parser.add_argument("question", nargs="*", help="Question to ask the agent.")
    parser.add_argument("--max-steps", type=int, default=10, help="Max tool-call rounds (default: 10).")
    parser.add_argument(
        "--log-turns",
        action="store_true",
        help="Print each assistant turn, including tool calls, as the agent runs.",
    )
    args = parser.parse_args()

    if args.question:
        question = " ".join(args.question)
    else:
        question = input("Question: ").strip()
        if not question:
            print("No question provided.")
            sys.exit(1)

    print()
    result = run_agent(question, max_steps=args.max_steps, log_turns=args.log_turns)
    print(result.final_answer)


if __name__ == "__main__":
    main()
