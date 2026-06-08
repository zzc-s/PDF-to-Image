"""PDF 批量转图片 GUI 工具。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from converter import QUALITY_PRESETS, convert_batch, estimate_page_pixels

APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = APP_DIR / "output"
DPI_OPTIONS = ["150", "200", "300", "400", "600"]
PRESET_OPTIONS = list(QUALITY_PRESETS.keys()) + ["自定义"]
DEFAULT_PRESET = "OCR 推荐"


class PdfToImageApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDF 转图片工具")
        self.root.geometry("720x600")
        self.root.minsize(640, 520)

        self.pdf_files: list[str] = []
        self.is_converting = False
        self._syncing_preset = False

        self.format_var = tk.StringVar(value="png")
        self.dpi_var = tk.StringVar(value="400")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.jpg_quality_var = tk.IntVar(value=90)
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))

        self._build_ui()
        self._update_jpg_quality_state()
        self._update_resolution_preview()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_frame = ttk.LabelFrame(main, text="PDF 文件", padding=8)
        file_frame.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(file_frame)
        button_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(button_row, text="添加 PDF", command=self._add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_row, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_row, text="清空列表", command=self._clear_files).pack(side=tk.LEFT)

        list_container = ttk.Frame(file_frame)
        list_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            yscrollcommand=scrollbar.set,
            height=8,
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)

        settings_frame = ttk.LabelFrame(main, text="转换设置", padding=8)
        settings_frame.pack(fill=tk.X, pady=10)

        output_row = ttk.Frame(settings_frame)
        output_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(output_row, text="输出目录:").pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.output_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8
        )
        ttk.Button(output_row, text="浏览...", command=self._browse_output_dir).pack(side=tk.LEFT)

        preset_row = ttk.Frame(settings_frame)
        preset_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(preset_row, text="清晰度预设:").pack(side=tk.LEFT)
        preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=PRESET_OPTIONS,
            width=12,
            state="readonly",
        )
        preset_combo.pack(side=tk.LEFT, padx=(8, 0))
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        format_row = ttk.Frame(settings_frame)
        format_row.pack(fill=tk.X)

        ttk.Label(format_row, text="格式:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            format_row,
            text="PNG",
            value="png",
            variable=self.format_var,
            command=self._on_manual_settings_changed,
        ).pack(side=tk.LEFT, padx=(8, 4))
        ttk.Radiobutton(
            format_row,
            text="JPG",
            value="jpg",
            variable=self.format_var,
            command=self._on_manual_settings_changed,
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(format_row, text="DPI:").pack(side=tk.LEFT)
        dpi_combo = ttk.Combobox(
            format_row,
            textvariable=self.dpi_var,
            values=DPI_OPTIONS,
            width=6,
            state="readonly",
        )
        dpi_combo.pack(side=tk.LEFT, padx=(8, 16))
        dpi_combo.bind("<<ComboboxSelected>>", self._on_manual_settings_changed)

        self.jpg_quality_label = ttk.Label(format_row, text="JPG 质量:")
        self.jpg_quality_label.pack(side=tk.LEFT)
        self.jpg_quality_scale = ttk.Scale(
            format_row,
            from_=80,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.jpg_quality_var,
            length=120,
        )
        self.jpg_quality_scale.pack(side=tk.LEFT, padx=8)
        self.jpg_quality_value_label = ttk.Label(format_row, text="90")
        self.jpg_quality_value_label.pack(side=tk.LEFT)
        self.jpg_quality_var.trace_add("write", self._update_quality_label)

        self.resolution_preview_label = ttk.Label(
            settings_frame,
            text="预计输出：添加 PDF 后显示像素尺寸",
            foreground="#555555",
        )
        self.resolution_preview_label.pack(fill=tk.X, pady=(8, 0))

        action_row = ttk.Frame(main)
        action_row.pack(fill=tk.X, pady=(0, 8))

        self.convert_button = ttk.Button(action_row, text="开始转换", command=self._start_conversion)
        self.convert_button.pack(fill=tk.X)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(action_row, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(8, 0))

        log_frame = ttk.LabelFrame(main, text="日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

    def _find_matching_preset(self) -> str:
        try:
            dpi = int(self.dpi_var.get())
        except ValueError:
            return "自定义"

        image_format = self.format_var.get()
        for name, settings in QUALITY_PRESETS.items():
            if settings["dpi"] == dpi and settings["format"] == image_format:
                return name
        return "自定义"

    def _on_preset_selected(self, _event=None) -> None:
        preset_name = self.preset_var.get()
        if preset_name == "自定义":
            return

        settings = QUALITY_PRESETS.get(preset_name)
        if not settings:
            return

        self._syncing_preset = True
        self.dpi_var.set(str(settings["dpi"]))
        self.format_var.set(str(settings["format"]))
        self._syncing_preset = False

        self._update_jpg_quality_state()
        self._update_resolution_preview()

    def _on_manual_settings_changed(self, _event=None) -> None:
        if self._syncing_preset:
            return

        self._syncing_preset = True
        self.preset_var.set(self._find_matching_preset())
        self._syncing_preset = False

        self._update_jpg_quality_state()
        self._update_resolution_preview()

    def _update_jpg_quality_state(self) -> None:
        is_jpg = self.format_var.get() == "jpg"
        state = tk.NORMAL if is_jpg else tk.DISABLED
        self.jpg_quality_scale.config(state=state)

    def _update_quality_label(self, *_args) -> None:
        self.jpg_quality_value_label.config(text=str(int(self.jpg_quality_var.get())))

    def _update_resolution_preview(self) -> None:
        if not self.pdf_files:
            self.resolution_preview_label.config(text="预计输出：添加 PDF 后显示像素尺寸")
            return

        try:
            dpi = int(self.dpi_var.get())
            width, height = estimate_page_pixels(self.pdf_files[0], dpi)
            self.resolution_preview_label.config(
                text=f"预计输出：约 {width} × {height} 像素/页（基于首个 PDF @ {dpi} DPI）"
            )
        except Exception as exc:
            self.resolution_preview_label.config(text=f"预计输出：无法计算（{exc}）")

    def _add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="选择 PDF 文件",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
        )
        if not selected:
            return

        existing = set(self.pdf_files)
        added = 0
        for path in selected:
            if path not in existing:
                self.pdf_files.append(path)
                existing.add(path)
                added += 1

        self._refresh_file_list()
        self._update_resolution_preview()
        if added:
            self._log(f"已添加 {added} 个 PDF 文件。")

    def _remove_selected(self) -> None:
        selected_indices = list(self.file_listbox.curselection())
        if not selected_indices:
            return

        for index in reversed(selected_indices):
            del self.pdf_files[index]

        self._refresh_file_list()
        self._update_resolution_preview()
        self._log("已移除选中的 PDF 文件。")

    def _clear_files(self) -> None:
        self.pdf_files.clear()
        self._refresh_file_list()
        self._update_resolution_preview()
        self._log("已清空文件列表。")

    def _refresh_file_list(self) -> None:
        self.file_listbox.delete(0, tk.END)
        for path in self.pdf_files:
            self.file_listbox.insert(tk.END, Path(path).name)

    def _browse_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            self.output_dir_var.set(selected)

    def _log(self, message: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_converting_state(self, converting: bool) -> None:
        self.is_converting = converting
        state = tk.DISABLED if converting else tk.NORMAL
        self.convert_button.config(state=state)

    def _update_progress(self, value: float) -> None:
        self.progress_var.set(value)

    def _start_conversion(self) -> None:
        if self.is_converting:
            return

        if not self.pdf_files:
            messagebox.showwarning("提示", "请先添加至少一个 PDF 文件。")
            return

        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showwarning("提示", "请设置输出目录。")
            return

        try:
            dpi = int(self.dpi_var.get())
        except ValueError:
            messagebox.showerror("错误", "DPI 设置无效。")
            return

        image_format = self.format_var.get()
        jpg_quality = int(self.jpg_quality_var.get())

        self._set_converting_state(True)
        self._update_progress(0)
        self._log("开始转换...")

        thread = threading.Thread(
            target=self._run_conversion,
            args=(list(self.pdf_files), output_dir, image_format, dpi, jpg_quality),
            daemon=True,
        )
        thread.start()

    def _run_conversion(
        self,
        pdf_files: list[str],
        output_dir: str,
        image_format: str,
        dpi: int,
        jpg_quality: int,
    ) -> None:
        total_files = len(pdf_files)
        completed_units = 0
        total_units = 0

        def on_file_start(pdf_path: str, file_index: int, file_count: int) -> None:
            nonlocal total_units
            try:
                import fitz

                with fitz.open(pdf_path) as doc:
                    total_units += len(doc)
            except Exception:
                total_units += 1

            self.root.after(
                0,
                lambda: self._log(
                    f"[{file_index}/{file_count}] 开始处理: {Path(pdf_path).name}"
                ),
            )

        def on_page(pdf_path: str, current_page: int, total_pages: int) -> None:
            nonlocal completed_units
            completed_units += 1
            progress = (completed_units / max(total_units, 1)) * 100
            self.root.after(
                0,
                lambda p=progress, name=Path(pdf_path).name, cp=current_page, tp=total_pages: (
                    self._update_progress(p),
                    self._log(f"  {name} - 第 {cp}/{tp} 页"),
                ),
            )

        def on_file_done(pdf_path: str, saved: list[str] | None, error: str | None) -> None:
            if error:
                self.root.after(
                    0,
                    lambda name=Path(pdf_path).name, err=error: self._log(
                        f"  失败: {name} ({err})"
                    ),
                )
            else:
                count = len(saved or [])
                self.root.after(
                    0,
                    lambda name=Path(pdf_path).name, c=count: self._log(
                        f"  完成: {name}，共 {c} 张图片"
                    ),
                )

        try:
            results = convert_batch(
                pdf_paths=pdf_files,
                output_root=output_dir,
                image_format=image_format,  # type: ignore[arg-type]
                dpi=dpi,
                jpg_quality=jpg_quality,
                on_file_start=on_file_start,
                on_page=on_page,
                on_file_done=on_file_done,
            )
        except Exception as exc:
            self.root.after(0, lambda: self._finish_conversion(False, str(exc)))
            return

        success_count = len(results["success"])
        failed_count = len(results["failed"])
        total_pages = results["total_pages"]
        summary = (
            f"转换完成：成功 {success_count} 个文件，失败 {failed_count} 个文件，"
            f"共生成 {total_pages} 张图片。"
        )
        self.root.after(0, lambda: self._finish_conversion(True, summary))

    def _finish_conversion(self, success: bool, message: str) -> None:
        self._update_progress(100 if success else self.progress_var.get())
        self._log(message)
        self._set_converting_state(False)

        if success:
            messagebox.showinfo("完成", message)
        else:
            messagebox.showerror("错误", message)


def main() -> None:
    root = tk.Tk()
    PdfToImageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
