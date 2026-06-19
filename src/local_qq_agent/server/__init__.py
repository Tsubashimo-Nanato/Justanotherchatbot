from __future__ import annotations


def __getattr__(name: str):
    if name == "create_app":
        from local_qq_agent.server.app import create_app

        return create_app
    raise AttributeError(name)

__all__ = ["create_app"]
