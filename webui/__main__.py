import argparse

from .server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(prog="webui", description="Local web UI for the LoL Insight Toolkit.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open it in your browser")
    args = parser.parse_args(argv)
    serve(args.port, args.open)


if __name__ == "__main__":
    main()
