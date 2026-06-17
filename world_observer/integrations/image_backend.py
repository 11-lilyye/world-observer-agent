from __future__ import annotations

from dataclasses import dataclass

from world_observer.visual_style import VisualPlan


@dataclass(frozen=True)
class ImageBackendResult:
    backend: str
    requested_backend: str
    ok: bool
    generated_files: list[str]
    note: str


class ImageBackend:
    def __init__(self, requested_backend: str = "canva_figma", fallback_backend: str = "prompt_only") -> None:
        self.requested_backend = requested_backend or "canva_figma"
        self.fallback_backend = fallback_backend or "prompt_only"

    def prepare(self, plan: VisualPlan) -> ImageBackendResult:
        backend = (self.requested_backend or plan.backend).strip().lower()
        if backend in {"prompt_only", "prompt"}:
            return ImageBackendResult(
                backend="prompt_only",
                requested_backend=self.requested_backend,
                ok=True,
                generated_files=[],
                note="已生成 cover_prompt.txt 和 image_prompts.json；未尝试生成图片。",
            )

        if backend in {"canva_figma", "canva", "figma"}:
            return ImageBackendResult(
                backend=self.fallback_backend,
                requested_backend=self.requested_backend,
                ok=True,
                generated_files=[],
                note=(
                    "Canva/Figma 作为默认视觉后端已预留。当前运行环境未提供可直接写入本地 PNG 的稳定接口，"
                    "因此本次 fallback 到 prompt_only。"
                ),
            )

        if backend in {"nano_banana", "image2", "comfyui"}:
            return ImageBackendResult(
                backend=self.fallback_backend,
                requested_backend=self.requested_backend,
                ok=True,
                generated_files=[],
                note=f"{self.requested_backend} 后端已预留但尚未配置 workflow，本次 fallback 到 prompt_only。",
            )

        return ImageBackendResult(
            backend=self.fallback_backend,
            requested_backend=self.requested_backend,
            ok=True,
            generated_files=[],
            note=f"未知图片后端 {self.requested_backend}，本次 fallback 到 prompt_only。",
        )
