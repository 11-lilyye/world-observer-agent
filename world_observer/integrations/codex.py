from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class CodexClient:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def available(self) -> bool:
        return shutil.which("codex") is not None

    def generate_text(self, prompt: str, fallback: str, timeout_seconds: int = 180) -> str:
        if not self.available():
            print("[Codex] unavailable: codex command not found", flush=True)
            return fallback

        with tempfile.TemporaryDirectory(prefix="world-observer-codex-") as tmp:
            output_path = Path(tmp) / "last_message.md"
            command = [
                "codex",
                "exec",
                "--cd",
                str(self.project_root),
                "--sandbox",
                "read-only",
                "--output-last-message",
                str(output_path),
                prompt,
            ]
            try:
                print(f"[Codex] generating text timeout={timeout_seconds}s", flush=True)
                subprocess.run(
                    command,
                    cwd=self.project_root,
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                print("[Codex] timeout", flush=True)
                return fallback
            except subprocess.CalledProcessError as error:
                stderr = (error.stderr or "").strip()
                print(f"[Codex] failed: {stderr[:500]}", flush=True)
                return fallback
            except OSError as error:
                print(f"[Codex] failed: {error}", flush=True)
                return fallback

            if not output_path.exists():
                print("[Codex] failed: output file missing", flush=True)
                return fallback
            text = output_path.read_text(encoding="utf-8", errors="ignore").strip()
            print(f"[Codex] done: {len(text)} chars", flush=True)
            return text or fallback

    def health(self) -> dict[str, object]:
        if not self.available():
            return {"ok": False, "detail": "codex command not found"}
        try:
            result = subprocess.run(
                ["codex", "--version"],
                cwd=self.project_root,
                check=True,
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            return {"ok": False, "detail": str(error)}
        return {"ok": True, "version": result.stdout.strip()}
