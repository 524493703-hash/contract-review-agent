from __future__ import annotations

import base64
from io import BytesIO
import sys
from pathlib import Path

import httpx
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import get_settings  # noqa: E402


def main() -> None:
    source = PROJECT_ROOT.parent / "KSOCM_合同模板" / "8.林德标版合同背面条款供参考.jpg"
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((1800, 1800))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    settings = get_settings()
    response = httpx.post(
        f"{settings.llm_api_url.rstrip('/')}/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "识别图片。只返回文档标题和前三个编号章节标题，不要解释。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                    ],
                }
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 300,
        },
        timeout=120,
    )
    if response.is_error:
        print(response.text)
    response.raise_for_status()
    print(response.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
