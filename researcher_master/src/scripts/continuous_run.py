"""Small script to run one continuous cycle (for cron or manual runs)."""
from src.continuous.manager import run_cycle


def main():
    res = run_cycle()
    print("Cycle result:", res)


if __name__ == '__main__':
    main()
