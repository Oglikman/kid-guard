"""Entry point the browser launches for native messaging; speaks length-prefixed JSON on stdin/stdout only."""
import sys

from kidguard import config
from kidguard.blocklist import load_blocklist
from kidguard.host import HostContext, serve


def main() -> int:
    """Loads the blocklists once, then serves browser requests over binary stdin/stdout until the browser disconnects."""
    ctx = HostContext(blocklist=load_blocklist(), log_path=config.HOST_LOG_PATH)
    serve(sys.stdin.buffer, sys.stdout.buffer, ctx)   # stdout must carry protocol frames only; never print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
