"""
app_en.py — English edition entry point

Run this file to launch a fully English web UI.
All shared logic (3D widget, API call, helpers) is imported from core.py.
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

# ====================== English strings ======================
T = {
    "title": "🎬 3D Camera Control · Multi-Angle Image Generation",
    "subtitle": "Upload an image → drag the 3D camera or use sliders → generate any viewpoint",
    "badge_api": "API Powered",
    "badge_3d": "3D Interactive",
    "badge_multi": "8×4 Views",
    "badge_realtime": "Live Preview",
    "input_panel": "📷 Input & Control",
    "input_label": "Input Image",
    "ctrl_title": "🎮 3D Camera Control",
    "ctrl_hint": "Drag the colored handles: 🟢 Azimuth / 🩷 Elevation / 🟠 Distance",
    "reset_btn": "🔄 Reset View",
    "preset_title": "⚡ Quick Presets",
    "run_btn": "🚀 Generate",
    "slider_title": "🎚️ Slider Controls",
    "az_label": "Azimuth (Horizontal Rotation)",
    "az_info": "0°=front  90°=right  180°=back  270°=left",
    "el_label": "Elevation (Vertical Angle)",
    "el_info": "-30°=low angle  0°=eye level  60°=high angle",
    "dist_label": "Distance",
    "dist_info": "0.6=close-up  1.0=medium  1.8=wide",
    "prompt_label": "Generated Prompt",
    "prompt_init": "<sks> front view eye-level shot medium shot",
    "output_panel": "🖼️ Output",
    "output_label": "Output Image",
    "output_placeholder": None,
    "history_label": "History",
    "adv_title": "⚙️ Advanced Settings",
    "seed_label": "Seed",
    "randomize_label": "Randomize Seed",
    "size_label": "Output Size",
    "size_info": "Format: width*height, e.g. 1024*1024",
    "neg_label": "Negative Prompt",
    "neg_info": "Elements you do not want in the result",
    "neg_default": " ",
    "preset_names": {
        "front": "Front",
        "right": "Right",
        "back": "Back",
        "left": "Left",
        "aerial": "Aerial",
        "closeup": "Close-up",
    },
    "err_no_image": "Please upload an image first",
    "err_api": "API error: {} - {}",
    "err_call": "Call failed: {}",
    "err_no_preset": "Please select at least one viewpoint",
    "download_label": "Download Result",
    "info_label": "Generation Info",
    "info_template": "**Prompt**: `{prompt}`\n\n**Seed**: {seed}\n\n**Size**: {size}\n\n**View**: {view}",
    "info_empty": "No generation yet. Click **Generate** and the info will appear here.",
    "batch_title": "🔀 Batch Viewpoint Generation",
    "batch_desc": "Select the viewpoints you want, and generate them all in one batch (sequential calls, billed per view)",
    "batch_choices": [
        ("Front view", "front"),
        ("Right view", "right"),
        ("Back view", "back"),
        ("Left view", "left"),
        ("Aerial view", "aerial"),
        ("Close-up", "closeup"),
    ],
    "batch_btn": "🚀 Batch Generate",
    "batch_gallery": "Batch Results",
    "batch_default": [],
    "view_desc": {
        "front": "Front / Eye-level / Medium",
        "right": "Right / Eye-level / Medium",
        "back": "Back / Eye-level / Medium",
        "left": "Left / Eye-level / Medium",
        "aerial": "Front / High-angle / Medium",
        "closeup": "Front / Eye-level / Close-up",
        "custom": "Custom view",
    },
    "foot": "Default backend: Qwen-Image-Edit-Plus · Replaceable with other image models · 3D control built with Three.js · Build your own open-source project",
    "example_title": "Example Image",
    "tab_main": "🎬 Main",
    "tab_history": "📚 History",
    "history_page_title": "History",
    "history_page_desc": "All generated results in this session (single and batch). Click an image to enlarge; download via the icon at the top-right corner.",
    "history_empty": "No history yet. Generate some on the Main tab!",
    "view_history_btn": "📚 View History",
    "clear_history_btn": "🗑️ Clear History",
    "history_cleared": "History cleared",
}


def make_preset_handler(az, el, dist):
    def handler():
        return (
            {"azimuth": az, "elevation": el, "distance": dist},
            az, el, dist,
        )
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

        # Session-level history state (avoids multi-user conflicts)
        history_state = gr.State([])

        with gr.Tabs() as tabs:
            # ==================== Tab 1: Main ====================
            with gr.Tab(T["tab_main"], id="main"):
                with gr.Row(equal_height=False):
                    # —— Left: input & control ——
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

                    # —— Right: output ——
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

            # ==================== Tab 2: History ====================
            with gr.Tab(T["tab_history"], id="history"):
                gr.Markdown(f"# {T['history_page_title']}\n\n{T['history_page_desc']}")
                history_gallery = gr.Gallery(
                    label=T["history_label"], columns=3, height=640,
                    show_label=False, object_fit="contain",
                )
                clear_history_btn = gr.Button(T["clear_history_btn"], variant="stop", size="sm")

        gr.Markdown(f'<div class="foot-note">{T["foot"]}</div>')

        # ====================== Event bindings ======================
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
            # Accumulate history
            hist_list = list(hist_list) if hist_list else []
            hist_list.insert(0, (url, f"seed={new_seed}"))
            # Info card
            view = T["view_desc"].get("custom", "Custom view")
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
            # Accumulate history (batch results prepended)
            hist_list = list(hist_list) if hist_list else []
            for url, key in results:
                hist_list.insert(0, (url, f"{T['preset_names'].get(key, key)}"))
            return results, hist_list, final_seed

        # 3D → sliders
        camera_3d.change(
            fn=sync_3d_to_sliders,
            inputs=[camera_3d],
            outputs=[azimuth_slider, elevation_slider, distance_slider],
        )

        # Slider release → 3D
        for slider in [azimuth_slider, elevation_slider, distance_slider]:
            slider.release(
                fn=sync_sliders_to_3d,
                inputs=[azimuth_slider, elevation_slider, distance_slider],
                outputs=[camera_3d],
            )

        # Preset buttons → 3D + sliders
        for btn, handler in zip(preset_buttons, preset_handlers):
            btn.click(
                fn=handler,
                inputs=[],
                outputs=[camera_3d, azimuth_slider, elevation_slider, distance_slider],
            )

        # Reset
        reset_btn.click(
            fn=on_reset,
            inputs=[],
            outputs=[camera_3d, azimuth_slider, elevation_slider, distance_slider],
        )

        # Generate
        run_btn.click(
            fn=on_run,
            inputs=[image, azimuth_slider, elevation_slider, distance_slider, seed, randomize_seed, size, negative_prompt, history_state],
            outputs=[result, seed, history_state, info_box],
        ).then(
            fn=lambda h: h,
            inputs=[history_state],
            outputs=[history_gallery],
        )

        # Batch generate
        batch_btn.click(
            fn=on_batch_run,
            inputs=[image, batch_check, seed, randomize_seed, size, negative_prompt, history_state],
            outputs=[batch_gallery, history_state, seed],
        ).then(
            fn=lambda h: h,
            inputs=[history_state],
            outputs=[history_gallery],
        )

        # View history → switch to History tab
        view_history_btn.click(
            fn=lambda: gr.Tabs(selected="history"),
            outputs=[tabs],
        )

        # Clear history
        clear_history_btn.click(
            fn=lambda: ([], []),
            outputs=[history_state, history_gallery],
        )

        # Upload → auto size + 3D texture
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
