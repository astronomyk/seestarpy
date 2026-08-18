"""``python -m seestarpy.dashboard`` — start the dashboard from the shell."""

import argparse

from .server import DEFAULT_PORT, serve


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m seestarpy.dashboard",
        description="Live dashboard for every Seestar on the local network.",
    )
    parser.add_argument("--host", default=None,
                        help="interface to bind (default: 127.0.0.1). "
                             "Overrides --lan.")
    parser.add_argument("--lan", action="store_true",
                        help="bind 0.0.0.0 so the dashboard is reachable "
                             "from the rest of the network. There is no "
                             "authentication, so only do this on a network "
                             "you trust.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port to serve on (default: {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open a browser window")
    parser.add_argument("--rescan", type=float, default=60.0, metavar="SECONDS",
                        help="seconds between network discovery sweeps "
                             "(default: 60)")
    parser.add_argument("--wide", action="store_true",
                        help="show the wide-angle camera (port 4804) instead "
                             "of the telephoto stream")
    parser.add_argument("--verbose", action="store_true",
                        help="log every HTTP request")
    args = parser.parse_args(argv)

    from .. import stream

    serve(
        host=args.host,
        lan=args.lan,
        port=args.port,
        open_browser=not args.no_browser,
        rescan_interval=args.rescan,
        image_port=stream.IMAGE_PORT_WIDE if args.wide else stream.IMAGE_PORT,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
