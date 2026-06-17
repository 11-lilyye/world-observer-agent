from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from world_observer.integrations.config import Settings
from world_observer.models import ImportedWechatArticle


class WechatArticleImporter:
    """Import WeChat articles into the local public-account source library.

    Preferred path: gxcsoccer/wechat-article-crawler.
    Fallback path: direct read-only HTTP fetch with a WeChat User-Agent.
    """

    REPO_URL = "https://github.com/gxcsoccer/wechat-article-crawler"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.project_root = Path(__file__).resolve().parents[2]

    def import_urls(self, urls: list[str]) -> list[ImportedWechatArticle]:
        return [self.import_url(url) for url in urls]

    def import_url(self, url: str) -> ImportedWechatArticle:
        if "mp.weixin.qq.com" not in url:
            raise ValueError(f"不是微信公众号文章 URL: {url}")

        article = self._crawl_with_external_crawler(url)
        if article:
            return article
        return self._crawl_with_direct_fetch(url)

    def health(self) -> dict[str, object]:
        script = self._crawler_script()
        return {
            "preferred": "gxcsoccer/wechat-article-crawler",
            "repo": self.REPO_URL,
            "crawler_configured": bool(script),
            "crawler_script": str(script) if script else None,
            "fallback": "direct MicroMessenger UA fetch",
        }

    def _crawl_with_external_crawler(self, url: str) -> ImportedWechatArticle | None:
        script = self._crawler_script()
        if not script:
            return None

        tmp_path = Path(tempfile.mkdtemp(prefix="woa-wechat-crawl-"))
        command = [
            self._crawler_python(),
            str(script),
            url,
            "--download-images",
            "--save-markdown",
            "--save-html",
            "--output-dir",
            str(tmp_path),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=script.parent.parent,
                check=True,
                text=True,
                capture_output=True,
                timeout=180,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

        markdown = self._read_largest(tmp_path, "*.md")
        raw_html = self._read_largest(tmp_path, "*.html")
        if not markdown:
            return None
        metadata = self._json_from_stdout(result.stdout) or self._read_json(tmp_path)
        title = metadata.get("title") or self._title_from_markdown(markdown) or self._title_from_html(raw_html) or "未命名公众号文章"
        images = [str(path) for path in sorted((tmp_path / "images").glob("*"))] if (tmp_path / "images").exists() else []
        return ImportedWechatArticle(
            title=self._clean(title),
            url=metadata.get("url") or url,
            author=self._clean(metadata.get("author") or ""),
            publish_time=self._clean(metadata.get("publish_time") or ""),
            account_desc=self._clean(metadata.get("account_desc") or ""),
            markdown=markdown.strip(),
            html=raw_html,
            images=images,
            importer="gxcsoccer/wechat-article-crawler",
        )

    def _crawl_with_direct_fetch(self, url: str) -> ImportedWechatArticle:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                    "MicroMessenger/8.0.43"
                ),
                "Referer": "https://mp.weixin.qq.com/",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_html = response.read().decode("utf-8", errors="ignore")
        except (OSError, urllib.error.URLError) as error:
            raise RuntimeError(f"公众号文章抓取失败: {error}") from error

        title = self._title_from_html(raw_html) or "未命名公众号文章"
        author = self._match_text(raw_html, r'id="js_name"[^>]*>(.*?)</')
        publish_time = self._match_text(raw_html, r'id="publish_time"[^>]*>(.*?)</')
        body = self._match_text(raw_html, r'id="js_content"[^>]*>(.*?)</div>')
        markdown = self._html_to_markdown(body or raw_html)
        return ImportedWechatArticle(
            title=self._clean(title),
            url=url,
            author=self._clean(author),
            publish_time=self._clean(publish_time),
            markdown=f"# {self._clean(title)}\n\n{markdown}".strip(),
            html=raw_html,
            importer="direct-fetch",
        )

    def _crawler_script(self) -> Path | None:
        candidates = [
            self._env_crawler_dir() / "scripts" / "crawl_wechat.py" if self._env_crawler_dir() else None,
            self.project_root / "external" / "wechat-article-crawler" / "scripts" / "crawl_wechat.py",
            self.project_root / ".claude" / "skills" / "crawl-wechat" / "scripts" / "crawl_wechat.py",
        ]
        for item in candidates:
            if item and item.exists():
                return item
        command = shutil.which("crawl_wechat.py")
        return Path(command) if command else None

    def _env_crawler_dir(self) -> Path | None:
        value = self._getenv("WECHAT_ARTICLE_CRAWLER_DIR")
        return Path(value).expanduser() if value else None

    def _crawler_python(self) -> str:
        configured = self._getenv("WECHAT_CRAWLER_PYTHON")
        if configured:
            return configured
        for name in ("python3.12", "python3.11", "python3"):
            command = shutil.which(name)
            if command:
                return command
        return "python3"

    def _getenv(self, key: str) -> str | None:
        import os

        return os.getenv(key)

    def _read_largest(self, root: Path, pattern: str) -> str:
        files = sorted(root.rglob(pattern), key=lambda path: path.stat().st_size if path.exists() else 0, reverse=True)
        if not files:
            return ""
        return files[0].read_text(encoding="utf-8", errors="ignore")

    def _read_json(self, root: Path) -> dict[str, str]:
        for path in sorted(root.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items() if value is not None}
        return {}

    def _json_from_stdout(self, stdout: str) -> dict[str, str]:
        match = re.search(r"\{.*?\}", stdout, flags=re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items() if value is not None}

    def _title_from_markdown(self, markdown: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def _title_from_html(self, raw_html: str) -> str:
        return self._match_text(raw_html, r'id="activity-name"[^>]*>(.*?)</') or self._match_text(raw_html, r"<title>(.*?)</title>")

    def _match_text(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.S | re.I)
        return self._clean(match.group(1)) if match else ""

    def _html_to_markdown(self, value: str) -> str:
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
        value = re.sub(r"</p\s*>", "\n\n", value, flags=re.I)
        value = re.sub(r"<img[^>]+(?:data-src|src)=[\"']([^\"']+)[\"'][^>]*>", r"\n\n![](\1)\n\n", value, flags=re.I)
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", value)).strip()

    def _clean(self, value: str) -> str:
        value = html.unescape(value or "")
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", value).strip()
