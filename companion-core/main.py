#!/usr/bin/env python3
import logging
import os
import signal
import sys

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("companion")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_banner(config: dict):
    port = config["web"]["port"]
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║         COMPANION CORE  v1.0         ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    print(f"  Web interface  →  http://0.0.0.0:{port}")
    print(f"  Local network  →  http://<your-ip>:{port}")
    print()
    print("  Press Ctrl+C to stop.")
    print()


def main():
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    if not os.path.isfile(config_path):
        logger.error("Config not found: %s", config_path)
        sys.exit(1)

    config = load_config(config_path)

    from modules.llm_server import LLMServer
    llm_server = LLMServer(config)

    logger.info("Starting LLM server (this may take ~30 seconds)...")
    try:
        llm_server.start()
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except TimeoutError as e:
        logger.error("%s", e)
        sys.exit(1)

    from modules.memory import MemoryManager
    memory = MemoryManager(config)

    from modules.brain import Brain
    brain = Brain(config, memory)

    from web.server import create_app
    app = create_app(config, brain)

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        llm_server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print_banner(config)

    app.run(
        host=config["web"]["host"],
        port=config["web"]["port"],
        debug=False,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
