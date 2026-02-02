import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemini Business cookie refresher")
    parser.add_argument("--once", action="store_true", help="Run one refresh cycle and exit")
    parser.add_argument("--schedule", action="store_true", help="Run in scheduled loop")
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
