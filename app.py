"""
app.py — 兼容入口

默认启动中文版。可通过命令行参数切换：
    python app.py          # 中文版（默认）
    python app.py zh       # 中文版
    python app.py en       # 英文版

也可以直接运行：
    python app_zh.py       # 中文版
    python app_en.py       # 英文版
"""

import sys

import gradio as gr


def main():
    lang = "zh"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip("-")
        if arg in ("en", "english"):
            lang = "en"
        elif arg in ("zh", "chinese", "cn"):
            lang = "zh"

    if lang == "en":
        print("Launching English edition...")
        from app_en import build_ui, THREE_JS_HEAD
    else:
        print("启动中文版...")
        from app_zh import build_ui, THREE_JS_HEAD

    from core import combined_css
    app = build_ui()
    app.launch(head=THREE_JS_HEAD, theme=gr.themes.Soft(), css=combined_css(), show_error=False)


if __name__ == "__main__":
    main()
