"""
llm_server.py — Manages the llama.cpp server process.
"""

import logging
import os
import signal
import subprocess
import time

import requests

logger = logging.getLogger(__name__)


class LLMServer:
    def __init__(self, config: dict):
        self.cfg = config["llm"]
        self.model_path = config["llm"]["model_path"]
        self.host = self.cfg["host"]
        self.port = self.cfg["port"]
        self.base_url = f"http://{self.host}:{self.port}"
        self.process = None
        self._llama_binary = self._find_binary()

    def _find_binary(self) -> str:
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "llama.cpp", "build", "bin", "llama-server"),
            os.path.expanduser("~/.local/bin/llama-server"),
            "/usr/local/bin/llama-server",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return os.path.abspath(path)
        return "llama-server"

    def start(self):
        if self.is_running():
            logger.info("LLM server already running at %s", self.base_url)
            return

        model_abs = os.path.abspath(self.model_path)
        if not os.path.isfile(model_abs):
            raise FileNotFoundError(
                f"Model not found: {model_abs}\n"
                "Run bash install.sh first."
            )

        cmd = [
            self._llama_binary,
            "--model", model_abs,
            "--host", self.host,
            "--port", str(self.port),
            "--ctx-size", str(self.cfg["context_size"]),
            "--threads", str(self.cfg["threads"]),
            "--n-gpu-layers", str(self.cfg["gpu_layers"]),
            "--parallel", "2",
            "--cont-batching",
            "--log-disable",
        ]

        logger.info("Starting LLM server...")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )

        self._wait_until_ready(timeout=120)
        logger.info("LLM server ready at %s", self.base_url)

    def _wait_until_ready(self, timeout: int = 120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_running():
                return
            time.sleep(2)
        raise TimeoutError(
            f"LLM server did not start within {timeout}s."
        )

    def is_running(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def stop(self):
        if self.process and self.process.poll() is None:
            logger.info("Stopping LLM server...")
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait(timeout=10)
            self.process = None

    def chat_completions_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"
