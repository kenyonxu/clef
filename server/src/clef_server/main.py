"""Clef Server entry point."""

import uvicorn


def main():
    uvicorn.run(
        "clef_server.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8900,
        reload=True,
    )


if __name__ == "__main__":
    main()
