"""Run the match API: `python -m matchmind.api` or `matchmind-api`.

Host and port come from MATCHMIND_HOST (default 127.0.0.1) and PORT or
MATCHMIND_PORT (default 8000). Set MATCHMIND_HOST=0.0.0.0 inside a container.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT") or os.environ.get("MATCHMIND_PORT") or "8000")
    uvicorn.run(
        "matchmind.api.app:app",
        host=os.environ.get("MATCHMIND_HOST", "127.0.0.1"),
        port=port,
        ws_max_size=16 * 1024,  # the app answers anything over 4 KB with a plain ERROR
        proxy_headers=True,
        server_header=False,
    )


if __name__ == "__main__":
    main()
