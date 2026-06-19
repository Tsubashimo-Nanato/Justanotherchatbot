from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from local_qq_agent.config import ModelConfig
from local_qq_agent.model.manager import download_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the configured GGUF model.")
    parser.add_argument("--profile", default="", help="Model profile name from config/model.yaml.")
    args = parser.parse_args()

    config = ModelConfig.load_for_profile(args.profile or None)
    result = download_model(config)
    print(json.dumps({"profile": config.active_profile, "model": config.model, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
