"""PDF 转图片核心转换逻辑。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable, Literal

import fitz
from PIL import Image

ImageFormat = Literal["png", "jpg"]

QUALITY_PRESETS: dict[str, dict[str, int | str]] = {
    "快速预览": {"dpi": 150, "format": "png"},
    "标准": {"dpi": 200, "format": "png"},
    "高清": {"dpi": 300, "format": "png"},
    "OCR 推荐": {"dpi": 400, "format": "png"},
    "超清": {"dpi": 600, "format": "png"},
}


def estimate_page_pixels(pdf_path: str | Path, dpi: int) -> tuple[int, int]:
    """根据 PDF 第一页渲染结果获取输出像素宽高（与 convert_pdf 一致）。"""
    with fitz.open(pdf_path) as doc:
        pixmap = doc[0].get_pixmap(dpi=dpi, alpha=False)
        return pixmap.width, pixmap.height


def convert_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    image_format: ImageFormat = "png",
    dpi: int = 150,
    jpg_quality: int = 90,
    name_prefix: str | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> list[str]:
    """将单个 PDF 的每一页转为图片，返回已保存文件路径列表。"""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    ext = "png" if image_format == "png" else "jpg"

    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)
        for page_index, page in enumerate(doc):
            if on_page:
                on_page(page_index + 1, total_pages)

            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            page_name = f"page_{page_index + 1:03d}.{ext}"
            filename = f"{name_prefix}_{page_name}" if name_prefix else page_name
            output_path = output_dir / filename

            if image_format == "png":
                pixmap.save(output_path)
            else:
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                if image.mode in ("RGBA", "LA", "P"):
                    image = image.convert("RGB")
                image.save(output_path, format="JPEG", quality=jpg_quality)

            saved_paths.append(str(output_path))

    return saved_paths


def convert_batch(
    pdf_paths: list[str | Path],
    output_root: str | Path,
    image_format: ImageFormat = "png",
    dpi: int = 150,
    jpg_quality: int = 90,
    on_file_start: Callable[[str, int, int], None] | None = None,
    on_page: Callable[[str, int, int], None] | None = None,
    on_file_done: Callable[[str, list[str] | None, str | None], None] | None = None,
) -> dict:
    """批量转换多个 PDF，返回成功/失败统计。"""
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    results = {
        "success": [],
        "failed": [],
        "total_pages": 0,
    }

    total_files = len(pdf_paths)
    for file_index, pdf_path in enumerate(pdf_paths):
        pdf_path = Path(pdf_path)
        if on_file_start:
            on_file_start(str(pdf_path), file_index + 1, total_files)

        try:
            def page_callback(current_page: int, total_pages: int) -> None:
                if on_page:
                    on_page(str(pdf_path), current_page, total_pages)

            saved = convert_pdf(
                pdf_path=pdf_path,
                output_dir=output_root,
                image_format=image_format,
                dpi=dpi,
                jpg_quality=jpg_quality,
                name_prefix=pdf_path.stem,
                on_page=page_callback,
            )
            results["success"].append({"pdf": str(pdf_path), "images": saved})
            results["total_pages"] += len(saved)

            if on_file_done:
                on_file_done(str(pdf_path), saved, None)
        except Exception as exc:
            error_message = str(exc)
            results["failed"].append({"pdf": str(pdf_path), "error": error_message})
            if on_file_done:
                on_file_done(str(pdf_path), None, error_message)

    return results
