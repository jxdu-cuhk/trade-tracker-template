from __future__ import annotations

from pathlib import Path

from .names import save_name_cache
from .patcher import patch_core
from .runtime import APP_DIR, PROJECT_ROOT, emit_progress, load_core_module
from .styling import compact_preview_table_spacing, tidy_preview_table_currency_labels


def main() -> None:
    emit_progress("载入生成器", "加载交易看板生成模块。", 3)
    core = load_core_module()
    args = core.parse_args()
    output_path = Path(args.output)
    try:
        is_default_output = output_path == Path("preview") or output_path.resolve() == (PROJECT_ROOT / "preview").resolve()
    except OSError:
        is_default_output = output_path == Path("preview")
    if is_default_output:
        args.output = APP_DIR / "preview"
    emit_progress("检查工作簿", f"准备读取 {args.input.resolve().name}。", 6)
    patch_core(core, args.input.resolve())
    try:
        emit_progress("生成网页", "正在重新计算表格、图表和汇总数据。", 36)
        core.export_preview(args.input.resolve(), args.output.resolve(), args.min_rows, args.extra_rows)
        emit_progress("整理页面", "清理表格币种显示和行列间距。", 86)
        tidy_preview_table_currency_labels(args.output.resolve())
        compact_preview_table_spacing(args.output.resolve())
    finally:
        emit_progress("保存缓存", "保存标的名称缓存，减少下次查询。", 96)
        save_name_cache()
    emit_progress("完成", "网页已生成，可以重新载入预览。", 100)
