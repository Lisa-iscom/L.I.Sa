"""
brain.py — Core response generation.

Context sent to LLM (strictly):
  1. System prompt = SOUL + facts.json + relationship.md
  2. Last 20 dialogue messages
  3. Current user message
"""

import json
import logging
import os
import re
import threading
from typing import Generator

import requests

from modules.memory import MemoryManager

logger = logging.getLogger(__name__)

SOUL_CUSTOM_PATH = "SOUL_custom.md"
SOUL_DEFAULT_PATH = "SOUL.md"
SOUL_FALLBACK = "You are a warm, intelligent AI companion. Respond naturally."


class Brain:
    def __init__(self, config: dict, memory: MemoryManager):
        self.cfg = config
        self.llm_cfg = config["llm"]
        self.memory = memory
        self.soul = self._load_soul()
        self._chat_url = (
            f"http://{self.llm_cfg['host']}:{self.llm_cfg['port']}"
            f"/v1/chat/completions"
        )

    def _load_soul(self) -> str:
        for path in (SOUL_CUSTOM_PATH, SOUL_DEFAULT_PATH):
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path):
                continue
            with open(abs_path, "r", encoding="utf-8") as f:
                raw = f.read()
            stripped = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
            if stripped:
                logger.info("Loaded soul from: %s", path)
                return raw.strip()
        logger.warning("No SOUL file found, using fallback.")
        return SOUL_FALLBACK

    def stream_response(self, user_message: str) -> Generator[str, None, None]:
        system_prompt = self.memory.build_system_prompt(self.soul)
        history = self.memory.get_recent_messages()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "local",
            "messages": messages,
            "max_tokens": self.llm_cfg["max_tokens"],
            "temperature": self.llm_cfg["temperature"],
            "top_p": self.llm_cfg["top_p"],
            "repeat_penalty": self.llm_cfg["repeat_penalty"],
            "stream": True,
        }

        full_response = ""

        try:
            with requests.post(
                self._chat_url,
                json=payload,
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    chunk_str = decoded[6:]
                    if chunk_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_str)
                        text = chunk["choices"][0]["delta"].get("content", "")
                        if text:
                            full_response += text
                            yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

        except requests.exceptions.ConnectionError:
            yield "⚠️ Cannot connect to LLM server. Is it running?"
            return
        except Exception as e:
            yield f"⚠️ Error: {e}"
            return

        if not full_response:
            return

        self.memory.append_turn("user", user_message)
        self.memory.append_turn("assistant", full_response)

        self._run_memory_analysis_async()

    def _run_memory_analysis_async(self):
        recent = self.memory.get_recent_messages()
        if len(recent) < 2:
            return
        t = threading.Thread(
            target=self.memory.analyze_and_update,
            args=(recent,),
            daemon=True,
            name="memory-analysis",
        )
        t.start()
