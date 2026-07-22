"""Console chat with LARA: python -m src.app.cli"""
from .agent import build_agent, ask
from .config import AGENT_NAME

BANNER = f"""
{AGENT_NAME} — Latram Shop internal support agent
   Ask in English or Spanish. Type 'exit' to quit.
"""

def main() -> None:
    agent = build_agent()
    print(BANNER)
    while True:
        try:
            q = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"exit", "quit", "salir"}:
            break
        try:
            print(f"\n{AGENT_NAME} > {ask(agent, q)}\n")
        except Exception as exc:  # surface provider/rate-limit errors nicely
            print(f"\n[error] {exc}\n")

if __name__ == "__main__":
    main()
