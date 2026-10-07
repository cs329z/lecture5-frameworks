"""Run the calendar server: `python -m tinycal [--port 8765] [--no-browser]`."""

import argparse
import webbrowser

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the tinycal calendar server.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open the UI in a browser")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    print(f"tinycal running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        serve(args.port)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
