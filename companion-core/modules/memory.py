"""
memory.py — Persistent memory management.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, config: dict):
        self.cfg = config
        self.mem_cfg = config["memory"]
        self.llm_cfg = config["llm"]

        self.facts_path = self.mem_cfg["facts_file"]
        self.relationship_path = self.mem_cfg["relationship_file"]
        self.moments_path = self.mem_cfg["moments_file"]
        self.dialogue_path = self.mem_cfg["dialogue_file"]

        self.max_turns = self.mem_cfg["max_dialogue_turns"]

        self._ensure_files()

    def _ensure_files(self):
        for path in [self.facts_path, self.relationship_path,
                     self.moments_path, self.dialogue_path]:
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        if not os.path.exists(self.facts_path):
            self._write_json(self.facts_path, {})
        if not os.path.exists(self.dialogue_path):
            self._write_json(self.dialogue_path, [])
        for path in [self.relationship_path, self.moments_path]:
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")

    def _read_json(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_json(self, path: str, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_text(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _write_text(self, path: str, text: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def load_dialogue(self) -> list:
        data = self._read_json(self.dialogue_path)
        return data if isinstance(data, list) else []

    def save_dialogue(self, messages: list):
        trimmed = messages[-self.max_turns:]
        self._write_json(self.dialogue_path, trimmed)

    def append_turn(self, role: str, content: str):
        dialogue = self.load_dialogue()
        dialogue.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.save_dialogue(dialogue)

    def build_system_prompt(self, soul: str) -> str:
        facts = self._read_json(self.facts_path)
        relationship = self._read_text(self.relationship_path)

        facts_clean = {k: v for k, v in facts.items()
                       if not k.startswith("_") and v not in (None, [], {})}

        parts = [soul.strip()]

        if facts_clean:
            parts.append(
                "## What you know about the user\n" +
                json.dumps(facts_clean, ensure_ascii=False, indent=2)
            )

        if relationship.strip():
            parts.append("## Relationship history\n" + relationship)

        return "\n\n---\n\n".join(parts)

    def get_recent_messages(self) -> list:
        dialogue = self.load_dialogue()
        return [
            {"role": m["role"], "content": m["content"]}
            for m in dialogue
            if m.get("role") in ("user", "assistant")
        ]

    def analyze_and_update(self, conversation: list):
        if len(conversation) < 2:
            return

        llm_url = f"http://{self.llm_cfg['host']}:{self.llm_cfg['port']}/v1/chat/completions"

        try:
            r = requests.get(
                f"http://{self.llm_cfg['host']}:{self.llm_cfg['port']}/health",
                timeout=3
            )
            if r.status_code != 200:
                return
        except Exception:
            return

        current_facts = self._read_json(self.facts_path)
        current_facts_clean = {k: v for k, v in current_facts.items()
                                if not k.startswith("_")}

        conv_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in conversation[-20:]
            if m.get("role") in ("user", "assistant")
        )

        analysis_prompt = f"""You are a memory analysis system. Analyze the conversation and return ONLY valid JSON.

Current known facts:
{json.dumps(current_facts_clean, ensure_ascii=False, indent=2)}

Conversation:
{conv_text}

Return JSON in exactly this format (no markdown, no explanation):
{{
  "new_facts": {{
    "name": "name if mentioned or null",
    "occupation": "job if mentioned or null",
    "interests": ["interests if mentioned"],
    "misc": {{"key": "value for any other facts"}}
  }},
  "emotional_moment": "description of important emotional moment if any, or null",
  "relationship_update": "1-2 sentences about how the relationship developed, or null",
  "has_changes": true
}}"""

        try:
            resp = requests.post(
                llm_url,
                json={
                    "model": "local",
                    "messages": [{"role": "user", "content": analysis_prompt}],
                    "max_tokens": 512,
                    "temperature": 0.1,
                    "stream": False,
                },
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            analysis = self._parse_json_safe(raw)

            if analysis and analysis.get("has_changes"):
                self._apply_analysis(analysis)
                logger.info("Memory updated.")

        except Exception as e:
            logger.warning("Memory analysis failed: %s", e)

    def _parse_json_safe(self, text: str) -> Optional[dict]:
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _apply_analysis(self, analysis: dict):
        new_facts = analysis.get("new_facts", {})
        if new_facts:
            existing = self._read_json(self.facts_path)
            if not isinstance(existing, dict):
                existing = {}

            for key, value in new_facts.items():
                if value is None or value == [] or value == {}:
                    continue
                if key == "interests" and isinstance(value, list):
                    current = existing.get("interests", [])
                    existing["interests"] = list(dict.fromkeys(current + value))
                elif key == "misc" and isinstance(value, dict):
                    existing.setdefault("misc", {}).update(
                        {k: v for k, v in value.items() if v is not None}
                    )
                else:
                    existing[key] = value

            self._write_json(self.facts_path, existing)

        moment = analysis.get("emotional_moment")
        if moment:
            existing_moments = self._read_text(self.moments_path)
            timestamp = datetime.now().strftime("%Y-%m-%d")
            self._write_text(self.moments_path,
                             existing_moments + f"\n## {timestamp}\n{moment}\n")

        rel_update = analysis.get("relationship_update")
        if rel_update:
            existing_rel = self._read_text(self.relationship_path)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._write_text(self.relationship_path,
                             existing_rel + f"\n\n### {timestamp}\n{rel_update}")
