from sakuraplayer.shared.runtime import guarded_main, run_process


def main() -> None:
    run_process("worker")


if __name__ == "__main__":
    guarded_main("worker", main)
