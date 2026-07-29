"""
app_zh.py — 中文版入口

运行后网页界面为纯中文。
依赖 core.py 提供的共享逻辑（3D 控件、API 调用、工具函数）。
"""

import gradio as gr

from core import (
    CameraControl3D,
    MAX_SEED,
    PRESETS,
    PRESET_MAP,
    THREE_JS_HEAD,
    combined_css,
    infer_camera_edit,
    batch_infer_camera_edit,
    update_dimensions_on_upload,
    image_to_data_url,
)

# ====================== 中文文案 ======================
T = {
    "title": "🎬 3D 相机视角控制 · 多角度图像生成",
    "subtitle": "上传图片 → 拖动 3D 相机或使用滑块 → 一键生成任意视角",
    "badge_api": "API 调用",
    "badge_3d": "3D 交互",
    "badge_multi": "8×4 视角",
    "badge_realtime": "实时预览",
    "input_panel": "📷 输入与控制",
    "input_label": "上传图片",
    "ctrl_title": "🎮 3D 相机控制",
    "ctrl_hint": "拖动彩色手柄：🟢 方位角 / 🩷 仰角 / 🟠 距离",
    "reset_btn": "🔄 重置视角",
    "preset_title": "⚡ 快捷预设",
    "run_btn": "🚀 生成新视角",
    "slider_title": "🎚️ 滑块精调",
    "az_label": "方位角（水平旋转）",
    "az_info": "0°=正面  90°=右侧  180°=背面  270°=左侧",
    "el_label": "仰角（垂直角度）",
    "el_info": "-30°=低角度  0°=平视  60°=俯视",
    "dist_label": "距离",
    "dist_info": "0.6=特写  1.0=中景  1.8=远景",
    "prompt_label": "生成提示词",
    "prompt_init": "<sks> front view eye-level shot medium shot",
    "output_panel": "🖼️ 生成结果",
    "output_label": "输出图像",
    "output_placeholder": None,
    "history_label": "历史记录",
    "adv_title": "⚙️ 高级设置",
    "seed_label": "随机种子",
    "randomize_label": "随机化种子",
    "size_label": "输出尺寸",
    "size_info": "格式：宽*高，如 1024*1024",
    "neg_label": "负向提示词",
    "neg_info": "不想在结果中出现的元素",
    "neg_default": " ",
    "preset_names": {
        "front": "前视",
        "right": "右视",
        "back": "后视",
        "left": "左视",
        "aerial": "俯视",
        "closeup": "特写",
    },
    "err_no_image": "请先上传图片",
    "err_api": "API 错误：{} - {}",
    "err_call": "调用失败：{}",
    "err_no_preset": "请至少勾选一个视角",
    "download_label": "下载当前结果",
    "info_label": "本次生成信息",
    "info_template": "**提示词**：`{prompt}`\n\n**种子**：{seed}\n\n**尺寸**：{size}\n\n**视角**：{view}",
    "info_empty": "尚无生成结果，点击「生成新视角」后此处显示信息。",
    "batch_title": "🔀 批量视角生成",
    "batch_desc": "勾选想要的视角，一次批量生成多张图（串行调用，按视角数量计费）",
    "batch_choices": [
        ("前视 front", "front"),
        ("右视 right", "right"),
        ("后视 back", "back"),
        ("左视 left", "left"),
        ("俯视 aerial", "aerial"),
        ("特写 closeup", "closeup"),
    ],
    "batch_btn": "🚀 批量生成",
    "batch_gallery": "批量结果",
    "batch_default": [],
    "view_desc": {
        "front": "前视 / 平视 / 中景",
        "right": "右视 / 平视 / 中景",
        "back": "后视 / 平视 / 中景",
        "left": "左视 / 平视 / 中景",
        "aerial": "前视 / 俯视 / 中景",
        "closeup": "前视 / 平视 / 特写",
        "custom": "自定义视角",
    },
    "foot": "默认 Qwen-Image-Edit-Plus 后端 · 可替换其他生图模型 · 3D 控制基于 Three.js · 打造你的开源项目",
    "example_title": "示例图片",
    "tab_main": "🎬 主页",
    "tab_history": "📚 历史记录",
    "history_page_title": "历史记录",
    "history_page_desc": "本会话所有生成结果（含单次与批量）。点击图片可放大查看，图片右上角可下载。",
    "history_empty": "暂无历史记录，去主页生成一些吧～",
    "view_history_btn": "📚 查看历史记录",
    "clear_history_btn": "🗑️ 清空历史",
    "history_cleared": "历史已清空",
}


def make_preset_handler(az, el, dist):
    def handler():
        return {
            "azimuth": az,
            "elevation": el,
            "distance": dist,
        }, az, el, dist
    return handler


def build_ui():
    with gr.Blocks(title=T["title"]) as demo:

        # —— Hero ——
        gr.Markdown(f"# {T['title']}\n\n{T['subtitle']}")
        gr.Markdown(
            f'<div class="hero-badges">'
            f'<span class="badge badge-blue">{T["badge_api"]}</span>'
            f'<span class="badge badge-green">{T["badge_3d"]}</span>'
            f'<span class="badge badge-purple">{T["badge_multi"]}</span>'
            f'<span class="badge badge-blue">{T["badge_realtime"]}</span>'
            f'</div>'
        )

        # 会话级历史状态（避免多用户冲突）
        history_state = gr.State([])

        with gr.Tabs() as tabs:
            # ==================== Tab 1: 主页 ====================
            with gr.Tab(T["tab_main"], id="main"):
                with gr.Row(equal_height=False):
                    # —— 左：输入与控制 ——
                    with gr.Column(scale=1, elem_id="col-container"):
                        gr.Markdown(f"## {T['input_panel']}")
                        image = gr.Image(label=T["input_label"], type="pil", height=300)

                        with gr.Accordion(T["example_title"], open=False):
                            gr.Examples(
                                examples=[["1.png"]],
                                inputs=image,
                                cache_examples=False,
                            )

                        gr.Markdown(f"### {T['preset_title']}")
                        preset_buttons = []
                        preset_handlers = []
                        with gr.Row():
                            for key, az, el, dist in PRESETS:
                                btn = gr.Button(T["preset_names"][key], size="sm", elem_classes="preset-btn")
                                preset_buttons.append(btn)
                                preset_handlers.append(make_preset_handler(az, el, dist))

                        gr.Markdown(f"### {T['ctrl_title']}\n*{T['ctrl_hint']}*")
                        camera_3d = CameraControl3D(
                            value={"azimuth": 0, "elevation": 0, "distance": 1.0},
                            elem_id="camera-3d-control",
                        )
                        reset_btn = gr.Button(T["reset_btn"], size="sm")

                        run_btn = gr.Button(T["run_btn"], variant="primary", size="lg")

                        with gr.Accordion(T["slider_title"], open=True):
                            azimuth_slider = gr.Slider(
                                label=T["az_label"], minimum=0, maximum=315, step=45, value=0, info=T["az_info"]
                            )
                            elevation_slider = gr.Slider(
                                label=T["el_label"], minimum=-30, maximum=60, step=30, value=0, info=T["el_info"]
                            )
                            distance_slider = gr.Slider(
                        label=T["dist_label"], minimum=0.6, maximum=1.8, step=0.05, value=1.0, info=T["dist_info"]
                    )

                    # —— 右：输出 ——
                    with gr.Column(scale=1, elem_id="col-container"):
                        gr.Markdown(f"## {T['output_panel']}")

                        result = gr.Image(label=T["output_label"], height=420, interactive=False)

                        info_box = gr.Markdown(
                            T["info_empty"], elem_classes="info-card"
                        )

                        view_history_btn = gr.Button(T["view_history_btn"], variant="secondary", size="sm")

                        with gr.Accordion(T["batch_title"], open=False):
                            gr.Markdown(f"*{T['batch_desc']}*")
                            batch_check = gr.CheckboxGroup(
                                choices=T["batch_choices"],
                                value=T["batch_default"],
                                label=T["preset_title"],
                            )
                            batch_btn = gr.Button(T["batch_btn"], variant="secondary", size="lg")
                            batch_gallery = gr.Gallery(
                                label=T["batch_gallery"], columns=3, height=280, show_label=True
                            )

                        with gr.Accordion(T["adv_title"], open=False):
                            seed = gr.Slider(label=T["seed_label"], minimum=0, maximum=MAX_SEED, step=1, value=0)
                            randomize_seed = gr.Checkbox(label=T["randomize_label"], value=True)
                            size = gr.Textbox(label=T["size_label"], value="1024*1024", info=T["size_info"])
                            negative_prompt = gr.Textbox(
                                label=T["neg_label"], value=T["neg_default"], info=T["neg_info"]
                            )

            # ==================== Tab 2: 历史记录 ====================
            with gr.Tab(T["tab_history"], id="history"):
                gr.Markdown(f"# {T['history_page_title']}\n\n{T['history_page_desc']}")
                history_gallery = gr.Gallery(
                    label=T["history_label"], columns=3, height=640,
                    show_label=False, object_fit="contain",
                )
                clear_history_btn = gr.Button(T["clear_history_btn"], variant="stop", size="sm")

        gr.Markdown(f'<div class="foot-note">{T["foot"]}</div>')

        # ====================== 事件绑定 ======================
        def sync_3d_to_sliders(camera_value):
            if camera_value and isinstance(camera_value, dict):
                az = camera_value.get('azimuth', 0)
                el = camera_value.get('elevation', 0)
                dist = camera_value.get('distance', 1.0)
                return az, el, dist
            return gr.update(), gr.update(), gr.update()

        def sync_sliders_to_3d(az, el, dist):
            return {"azimuth": az, "elevation": el, "distance": dist}

        def update_3d_image(img):
            data_url = image_to_data_url(img)
            return gr.update(imageUrl=data_url)

        def on_reset():
            return (
                {"azimuth": 0, "elevation": 0, "distance": 1.0},
                0, 0, 1.0,
            )

        def on_run(img, az, el, dist, sd, rs, sz, neg, hist_list):
            try:
                url, new_seed, prompt = infer_camera_edit(
                    img, az, el, dist, sd, rs, sz, neg
                )
            except gr.Error as e:
                msg = str(e)
                if msg.startswith("IMAGE_REQUIRED"):
                    raise gr.Error(T["err_no_image"])
                if msg.startswith("API_ERROR:"):
                    _, code, message = msg.split(":", 2)
                    raise gr.Error(T["err_api"].format(code, message))
                if msg.startswith("CALL_FAILED:"):
                    raise gr.Error(T["err_call"].format(msg.split(":", 1)[1]))
                raise
            # 累积历史
            hist_list = list(hist_list) if hist_list else []
            hist_list.insert(0, (url, f"seed={new_seed}"))
            # 信息卡
            view = T["view_desc"].get("custom", "自定义视角")
            for k, v in PRESET_MAP.items():
                if v == (az, el, dist):
                    view = T["view_desc"].get(k, view)
                    break
            info = T["info_template"].format(prompt=prompt, seed=new_seed, size=sz, view=view)
            return url, new_seed, hist_list, info

        def on_batch_run(img, keys, sd, rs, sz, neg, hist_list):
            try:
                results, final_seed = batch_infer_camera_edit(img, keys, sd, rs, sz, neg)
            except gr.Error as e:
                msg = str(e)
                if msg.startswith("IMAGE_REQUIRED"):
                    raise gr.Error(T["err_no_image"])
                if msg.startswith("NO_PRESET"):
                    raise gr.Error(T["err_no_preset"])
                if msg.startswith("API_ERROR:"):
                    _, code, message = msg.split(":", 2)
                    raise gr.Error(T["err_api"].format(code, message))
                if msg.startswith("CALL_FAILED:"):
                    raise gr.Error(T["err_call"].format(msg.split(":", 1)[1]))
                raise
            # 累积历史（批量结果插到最前）
            hist_list = list(hist_list) if hist_list else []
            for url, key in results:
                hist_list.insert(0, (url, f"{T['preset_names'].get(key, key)}"))
            return results, hist_list, final_seed

        # 3D → 滑块
        camera_3d.change(
            fn=sync_3d_to_sliders,
            inputs=[camera_3d],
            outputs=[azimuth_slider, elevation_slider, distance_slider],
        )

        # 滑块释放 → 3D
        for slider in [azimuth_slider, elevation_slider, distance_slider]:
            slider.release(
                fn=sync_sliders_to_3d,
                inputs=[azimuth_slider, elevation_slider, distance_slider],
                outputs=[camera_3d],
            )

        # 预设按钮 → 3D + 滑块
        for btn, handler in zip(preset_buttons, preset_handlers):
            btn.click(
                fn=handler,
                inputs=[],
                outputs=[camera_3d, azimuth_slider, elevation_slider, distance_slider],
            )

        # 重置
        reset_btn.click(
            fn=on_reset,
            inputs=[],
            outputs=[camera_3d, azimuth_slider, elevation_slider, distance_slider],
        )

        # 生成
        run_btn.click(
            fn=on_run,
            inputs=[image, azimuth_slider, elevation_slider, distance_slider, seed, randomize_seed, size, negative_prompt, history_state],
            outputs=[result, seed, history_state, info_box],
        ).then(
            fn=lambda h: h,
            inputs=[history_state],
            outputs=[history_gallery],
        )

        # 批量生成
        batch_btn.click(
            fn=on_batch_run,
            inputs=[image, batch_check, seed, randomize_seed, size, negative_prompt, history_state],
            outputs=[batch_gallery, history_state, seed],
        ).then(
            fn=lambda h: h,
            inputs=[history_state],
            outputs=[history_gallery],
        )

        # 查看历史 → 切换到历史 Tab
        view_history_btn.click(
            fn=lambda: gr.Tabs(selected="history"),
            outputs=[tabs],
        )

        # 清空历史
        clear_history_btn.click(
            fn=lambda: ([], []),
            outputs=[history_state, history_gallery],
        )

        # 上传 → 尺寸自适应 + 3D 贴图
        image.upload(
            fn=update_dimensions_on_upload,
            inputs=[image],
            outputs=[size],
        ).then(
            fn=update_3d_image,
            inputs=[image],
            outputs=[camera_3d],
        )

        image.clear(fn=lambda: gr.update(imageUrl=None), outputs=[camera_3d])

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(head=THREE_JS_HEAD, theme=gr.themes.Soft(), css=combined_css(), show_error=False)
