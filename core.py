"""
core.py — 共享核心逻辑（中英文版共用）

包含：
- 相机参数映射表（送给模型的 prompt 始终是英文）
- 工具函数：prompt 构建、图像转 base64、尺寸自适应
- API 调用：DashScope qwen-image-edit-plus
- CameraControl3D：基于 Three.js 的 3D 相机控制器
- 全局 CSS 与 Three.js head 注入

本文件不含任何界面文案，界面文案由 app_zh.py / app_en.py 提供。
"""

import os
import base64
import random
import tempfile
import urllib.request
from io import BytesIO

import gradio as gr
import numpy as np
from PIL import Image

import dashscope
from dashscope import MultiModalConversation

# DashScope 服务地址
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

# API Key：优先环境变量，其次使用代码内默认值（开源部署请替换为自己的 Key）
API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY",
    "sk-your-api-key-here",
)

MAX_SEED = np.iinfo(np.int32).max

# —— 相机参数映射（送给模型的 prompt 必须是英文，与训练 LoRA 时一致）——
AZIMUTH_MAP = {
    0: "front view",
    45: "front-right quarter view",
    90: "right side view",
    135: "back-right quarter view",
    180: "back view",
    225: "back-left quarter view",
    270: "left side view",
    315: "front-left quarter view",
}

ELEVATION_MAP = {
    -30: "low-angle shot",
    0: "eye-level shot",
    30: "elevated shot",
    60: "high-angle shot",
}

DISTANCE_MAP = {
    0.6: "close-up",
    1.0: "medium shot",
    1.8: "wide shot",
}

# —— 快捷预设（azimuth, elevation, distance）——
PRESETS = [
    ("front", 0, 0, 1.0),
    ("right", 90, 0, 1.0),
    ("back", 180, 0, 1.0),
    ("left", 270, 0, 1.0),
    ("aerial", 0, 60, 1.0),
    ("closeup", 0, 0, 0.6),
]

# key → (az, el, dist) 反查表
PRESET_MAP = {key: (az, el, dist) for key, az, el, dist in PRESETS}


def snap_to_nearest(value, options):
    return min(options, key=lambda x: abs(x - value))


def build_camera_prompt(azimuth: float, elevation: float, distance: float) -> str:
    """根据相机参数构建送给模型的 prompt（英文，与 LoRA 训练时一致）。"""
    azimuth_snapped = snap_to_nearest(azimuth, list(AZIMUTH_MAP.keys()))
    elevation_snapped = snap_to_nearest(elevation, list(ELEVATION_MAP.keys()))
    distance_snapped = snap_to_nearest(distance, list(DISTANCE_MAP.keys()))
    return f"<sks> {AZIMUTH_MAP[azimuth_snapped]} {ELEVATION_MAP[elevation_snapped]} {DISTANCE_MAP[distance_snapped]}"


def image_to_base64_url(image: Image.Image) -> str:
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def update_dimensions_on_upload(image):
    """根据上传图片的宽高比，自动给出 8 的倍数的目标尺寸。"""
    if image is None:
        return "1024*1024"
    original_width, original_height = image.size
    if original_width > original_height:
        new_width = 1024
        new_height = int(1024 * (original_height / original_width))
    else:
        new_height = 1024
        new_width = int(1024 * (original_width / original_height))
    new_width = (new_width // 8) * 8
    new_height = (new_height // 8) * 8
    return f"{new_width}*{new_height}"


def infer_camera_edit(
    image,
    azimuth: float = 0.0,
    elevation: float = 0.0,
    distance: float = 1.0,
    seed: int = 0,
    randomize_seed: bool = True,
    size: str = "1024*1024",
    negative_prompt: str = " ",
):
    """调用 DashScope 的 qwen-image-edit-plus 生成新视角图像。"""
    if image is None:
        raise gr.Error("IMAGE_REQUIRED")
    prompt = build_camera_prompt(azimuth, elevation, distance)

    if randomize_seed:
        seed = random.randint(0, MAX_SEED)

    pil_image = image.convert("RGB") if isinstance(image, Image.Image) else Image.open(image).convert("RGB")
    image_url = image_to_base64_url(pil_image)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_url},
                {"text": prompt},
            ],
        }
    ]

    try:
        response = MultiModalConversation.call(
            api_key=API_KEY,
            model="qwen-image-edit-plus",
            messages=messages,
            stream=False,
            n=1,
            watermark=False,
            negative_prompt=negative_prompt or " ",
            prompt_extend=True,
            size=size,
        )
        if response.status_code == 200:
            result_url = response.output.choices[0].message.content[0]['image']
            return result_url, seed, prompt
        raise gr.Error(f"API_ERROR:{response.code}:{response.message}")
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"CALL_FAILED:{e}")


def batch_infer_camera_edit(
    image,
    preset_keys,
    seed: int = 0,
    randomize_seed: bool = True,
    size: str = "1024*1024",
    negative_prompt: str = " ",
):
    """批量生成多个视角的图像。

    返回: (results, final_seed)
      results = [(image_url, caption), ...]
    """
    if image is None:
        raise gr.Error("IMAGE_REQUIRED")
    if not preset_keys:
        raise gr.Error("NO_PRESET")

    results = []
    current_seed = seed
    for key in preset_keys:
        az, el, dist = PRESET_MAP[key]
        url, current_seed, prompt = infer_camera_edit(
            image, az, el, dist, current_seed, randomize_seed, size, negative_prompt
        )
        results.append((url, key))
    return results, current_seed


def download_image_to_temp(url, prefix="result"):
    """把远端结果图下载到本地临时文件，供 gr.File 下载。失败返回 None。"""
    if not url:
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{prefix}_")
        with urllib.request.urlopen(url, timeout=60) as r:
            with os.fdopen(fd, 'wb') as f:
                f.write(r.read())
        return path
    except Exception:
        return None


# ====================== 3D 相机控制器 ======================

# Three.js r128 CDN
THREE_JS_HEAD = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

# 3D 控件初始化 JS（无界面文案，纯交互逻辑）
CAMERA_3D_JS = r"""
(() => {
    const wrapper = element.querySelector('#camera-control-wrapper');
    const promptOverlay = element.querySelector('#prompt-overlay');
    const angleReadout = element.querySelector('#angle-readout');

    const initScene = () => {
        if (typeof THREE === 'undefined') { setTimeout(initScene, 100); return; }

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x1a1a1a);

        const camera = new THREE.PerspectiveCamera(50, wrapper.clientWidth / wrapper.clientHeight, 0.1, 1000);
        camera.position.set(4.5, 3, 4.5);
        camera.lookAt(0, 0.75, 0);

        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(wrapper.clientWidth, wrapper.clientHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        wrapper.insertBefore(renderer.domElement, promptOverlay);

        scene.add(new THREE.AmbientLight(0xffffff, 0.6));
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
        dirLight.position.set(5, 10, 5);
        scene.add(dirLight);

        scene.add(new THREE.GridHelper(8, 16, 0x333333, 0x222222));

        const CENTER = new THREE.Vector3(0, 0.75, 0);
        const BASE_DISTANCE = 1.6;
        const AZIMUTH_RADIUS = 2.4;
        const ELEVATION_RADIUS = 1.8;

        let azimuthAngle = props.value?.azimuth || 0;
        let elevationAngle = props.value?.elevation || 0;
        let distanceFactor = props.value?.distance || 1.0;

        const azimuthSteps = [0, 45, 90, 135, 180, 225, 270, 315];
        const elevationSteps = [-30, 0, 30, 60];
        const distanceSteps = [0.6, 1.0, 1.4];

        const azimuthNames = {
            0: 'front view', 45: 'front-right quarter view', 90: 'right side view',
            135: 'back-right quarter view', 180: 'back view', 225: 'back-left quarter view',
            270: 'left side view', 315: 'front-left quarter view'
        };
        const elevationNames = { '-30': 'low-angle shot', '0': 'eye-level shot', '30': 'elevated shot', '60': 'high-angle shot' };
        function distanceNameOf(d) {
            if (d < 0.8) return 'close-up';
            if (d < 1.2) return 'medium shot';
            return 'wide shot';
        }

        function snapToNearest(value, steps) {
            return steps.reduce((prev, curr) => Math.abs(curr - value) < Math.abs(prev - value) ? curr : prev);
        }

        function createPlaceholderTexture() {
            const canvas = document.createElement('canvas');
            canvas.width = 256; canvas.height = 256;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#3a3a4a'; ctx.fillRect(0, 0, 256, 256);
            ctx.fillStyle = '#ffcc99';
            ctx.beginPath(); ctx.arc(128, 128, 80, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#333';
            ctx.beginPath(); ctx.arc(100, 110, 10, 0, Math.PI * 2); ctx.arc(156, 110, 10, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = '#333'; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.arc(128, 130, 35, 0.2, Math.PI - 0.2); ctx.stroke();
            return new THREE.CanvasTexture(canvas);
        }

        let currentTexture = createPlaceholderTexture();
        const planeMaterial = new THREE.MeshBasicMaterial({ map: currentTexture, side: THREE.DoubleSide });
        let targetPlane = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.2), planeMaterial);
        targetPlane.position.copy(CENTER);
        scene.add(targetPlane);

        function updateTextureFromUrl(url) {
            if (!url) {
                planeMaterial.map = createPlaceholderTexture();
                planeMaterial.needsUpdate = true;
                scene.remove(targetPlane);
                targetPlane = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.2), planeMaterial);
                targetPlane.position.copy(CENTER);
                scene.add(targetPlane);
                return;
            }
            const loader = new THREE.TextureLoader();
            loader.crossOrigin = 'anonymous';
            loader.load(url, (texture) => {
                texture.minFilter = THREE.LinearFilter;
                texture.magFilter = THREE.LinearFilter;
                planeMaterial.map = texture;
                planeMaterial.needsUpdate = true;
                const img = texture.image;
                if (img && img.width && img.height) {
                    const aspect = img.width / img.height;
                    const maxSize = 1.5;
                    let planeWidth, planeHeight;
                    if (aspect > 1) { planeWidth = maxSize; planeHeight = maxSize / aspect; }
                    else { planeHeight = maxSize; planeWidth = maxSize * aspect; }
                    scene.remove(targetPlane);
                    targetPlane = new THREE.Mesh(new THREE.PlaneGeometry(planeWidth, planeHeight), planeMaterial);
                    targetPlane.position.copy(CENTER);
                    scene.add(targetPlane);
                }
            }, undefined, (err) => console.error('Failed to load texture:', err));
        }

        if (props.imageUrl) updateTextureFromUrl(props.imageUrl);

        const cameraGroup = new THREE.Group();
        // 机身（蓝色金属质感）
        const bodyMat = new THREE.MeshStandardMaterial({ color: 0x4a7ab8, metalness: 0.5, roughness: 0.4 });
        const body = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.26, 0.42), bodyMat);
        cameraGroup.add(body);
        // 镜头筒（银色）
        const lensMat = new THREE.MeshStandardMaterial({ color: 0x9aa0a6, metalness: 0.85, roughness: 0.2 });
        const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 0.24, 28), lensMat);
        lens.rotation.x = Math.PI / 2;
        lens.position.z = 0.3;
        cameraGroup.add(lens);
        // 镜头前端玻璃（黑色反光）
        const lensGlass = new THREE.Mesh(
            new THREE.CylinderGeometry(0.085, 0.085, 0.02, 28),
            new THREE.MeshStandardMaterial({ color: 0x0a0a0a, metalness: 0.95, roughness: 0.08 })
        );
        lensGlass.rotation.x = Math.PI / 2;
        lensGlass.position.z = 0.42;
        cameraGroup.add(lensGlass);
        // 镜头变焦环（深色细环）
        const zoomRing = new THREE.Mesh(
            new THREE.CylinderGeometry(0.105, 0.105, 0.05, 28),
            new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.7, roughness: 0.4 })
        );
        zoomRing.rotation.x = Math.PI / 2;
        zoomRing.position.z = 0.24;
        cameraGroup.add(zoomRing);
        // 取景器顶部突起
        const viewfinder = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.07, 0.12), bodyMat);
        viewfinder.position.set(0, 0.165, -0.06);
        cameraGroup.add(viewfinder);
        // 快门按钮（金色小圆柱）
        const shutter = new THREE.Mesh(
            new THREE.CylinderGeometry(0.028, 0.028, 0.022, 16),
            new THREE.MeshStandardMaterial({ color: 0xd4a543, metalness: 0.9, roughness: 0.15 })
        );
        shutter.rotation.x = Math.PI / 2;
        shutter.position.set(0.14, 0.15, -0.12);
        cameraGroup.add(shutter);
        // 闪光灯（白色发光小块）
        const flash = new THREE.Mesh(
            new THREE.BoxGeometry(0.07, 0.035, 0.02),
            new THREE.MeshStandardMaterial({ color: 0xf5f5f5, emissive: 0xfff4d6, emissiveIntensity: 0.35 })
        );
        flash.position.set(-0.13, 0.148, -0.2);
        cameraGroup.add(flash);
        // 右侧握把（凸起，便于握持感）
        const grip = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.24, 0.4), bodyMat);
        grip.position.set(0.21, -0.01, 0);
        cameraGroup.add(grip);
        // 模式拨盘（顶部圆形）
        const dial = new THREE.Mesh(
            new THREE.CylinderGeometry(0.045, 0.045, 0.02, 20),
            new THREE.MeshStandardMaterial({ color: 0x4a4a52, metalness: 0.6, roughness: 0.35 })
        );
        dial.rotation.x = Math.PI / 2;
        dial.position.set(-0.13, 0.15, -0.12);
        cameraGroup.add(dial);
        scene.add(cameraGroup);

        const azimuthRing = new THREE.Mesh(
            new THREE.TorusGeometry(AZIMUTH_RADIUS, 0.04, 16, 64),
            new THREE.MeshStandardMaterial({ color: 0x00ff88, emissive: 0x00ff88, emissiveIntensity: 0.3 })
        );
        azimuthRing.rotation.x = Math.PI / 2;
        azimuthRing.position.y = 0.05;
        scene.add(azimuthRing);

        const azimuthHandle = new THREE.Mesh(
            new THREE.SphereGeometry(0.18, 16, 16),
            new THREE.MeshStandardMaterial({ color: 0x00ff88, emissive: 0x00ff88, emissiveIntensity: 0.5 })
        );
        azimuthHandle.userData.type = 'azimuth';
        scene.add(azimuthHandle);

        const arcPoints = [];
        for (let i = 0; i <= 32; i++) {
            const angle = THREE.MathUtils.degToRad(-30 + (90 * i / 32));
            arcPoints.push(new THREE.Vector3(-0.8, ELEVATION_RADIUS * Math.sin(angle) + CENTER.y, ELEVATION_RADIUS * Math.cos(angle)));
        }
        const arcCurve = new THREE.CatmullRomCurve3(arcPoints);
        const elevationArc = new THREE.Mesh(
            new THREE.TubeGeometry(arcCurve, 32, 0.04, 8, false),
            new THREE.MeshStandardMaterial({ color: 0xff69b4, emissive: 0xff69b4, emissiveIntensity: 0.3 })
        );
        scene.add(elevationArc);

        const elevationHandle = new THREE.Mesh(
            new THREE.SphereGeometry(0.18, 16, 16),
            new THREE.MeshStandardMaterial({ color: 0xff69b4, emissive: 0xff69b4, emissiveIntensity: 0.5 })
        );
        elevationHandle.userData.type = 'elevation';
        scene.add(elevationHandle);

        const distanceLineGeo = new THREE.BufferGeometry();
        const distanceLine = new THREE.Line(distanceLineGeo, new THREE.LineBasicMaterial({ color: 0xffa500 }));
        scene.add(distanceLine);

        function updatePositions() {
            const distance = BASE_DISTANCE * distanceFactor;
            const azRad = THREE.MathUtils.degToRad(azimuthAngle);
            const elRad = THREE.MathUtils.degToRad(elevationAngle);
            const camX = distance * Math.sin(azRad) * Math.cos(elRad);
            const camY = distance * Math.sin(elRad) + CENTER.y;
            const camZ = distance * Math.cos(azRad) * Math.cos(elRad);
            cameraGroup.position.set(camX, camY, camZ);
            cameraGroup.lookAt(CENTER);
            azimuthHandle.position.set(AZIMUTH_RADIUS * Math.sin(azRad), 0.05, AZIMUTH_RADIUS * Math.cos(azRad));
            elevationHandle.position.set(-0.8, ELEVATION_RADIUS * Math.sin(elRad) + CENTER.y, ELEVATION_RADIUS * Math.cos(elRad));
            distanceLineGeo.setFromPoints([cameraGroup.position.clone(), CENTER.clone()]);
            const azSnap = snapToNearest(azimuthAngle, azimuthSteps);
            const elSnap = snapToNearest(elevationAngle, elevationSteps);
            const prompt = '<sks> ' + azimuthNames[azSnap] + ' ' + elevationNames[String(elSnap)] + ' ' + distanceNameOf(distanceFactor);
            if (promptOverlay) promptOverlay.textContent = prompt;
            if (angleReadout) angleReadout.textContent =
                'Az ' + Math.round(azimuthAngle) + '°  El ' + Math.round(elevationAngle) + '°  D ' + distanceFactor.toFixed(2);
        }

        function updatePropsAndTrigger() {
            const azSnap = snapToNearest(azimuthAngle, azimuthSteps);
            const elSnap = snapToNearest(elevationAngle, elevationSteps);
            props.value = { azimuth: azSnap, elevation: elSnap, distance: distanceFactor };
            trigger('change', props.value);
        }

        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let isDragging = false;
        let dragTarget = null;
        let dragStartMouse = new THREE.Vector2();
        let dragStartDistance = 1.0;
        const intersection = new THREE.Vector3();
        const canvas = renderer.domElement;

        function pickHandle(e) {
            const rect = canvas.getBoundingClientRect();
            const cx = e.clientX !== undefined ? e.clientX : e.touches[0].clientX;
            const cy = e.clientY !== undefined ? e.clientY : e.touches[0].clientY;
            mouse.x = ((cx - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((cy - rect.top) / rect.height) * 2 + 1;
            raycaster.setFromCamera(mouse, camera);
            return raycaster.intersectObjects([azimuthHandle, elevationHandle]);
        }

        function moveByMouse(e) {
            const rect = canvas.getBoundingClientRect();
            const cx = e.clientX !== undefined ? e.clientX : e.touches[0].clientX;
            const cy = e.clientY !== undefined ? e.clientY : e.touches[0].clientY;
            mouse.x = ((cx - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((cy - rect.top) / rect.height) * 2 + 1;
            if (isDragging && dragTarget) {
                raycaster.setFromCamera(mouse, camera);
                if (dragTarget.userData.type === 'azimuth') {
                    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.05);
                    if (raycaster.ray.intersectPlane(plane, intersection)) {
                        azimuthAngle = THREE.MathUtils.radToDeg(Math.atan2(intersection.x, intersection.z));
                        if (azimuthAngle < 0) azimuthAngle += 360;
                    }
                } else if (dragTarget.userData.type === 'elevation') {
                    const plane = new THREE.Plane(new THREE.Vector3(1, 0, 0), -0.8);
                    if (raycaster.ray.intersectPlane(plane, intersection)) {
                        const relY = intersection.y - CENTER.y;
                        const relZ = intersection.z;
                        elevationAngle = THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(Math.atan2(relY, relZ)), -30, 60);
                    }
                }
                updatePositions();
            } else {
                raycaster.setFromCamera(mouse, camera);
                const intersects = raycaster.intersectObjects([azimuthHandle, elevationHandle]);
                [azimuthHandle, elevationHandle].forEach(h => {
                    h.material.emissiveIntensity = 0.5; h.scale.setScalar(1);
                });
                if (intersects.length > 0) {
                    intersects[0].object.material.emissiveIntensity = 0.8;
                    intersects[0].object.scale.setScalar(1.1);
                    canvas.style.cursor = 'grab';
                } else { canvas.style.cursor = 'default'; }
            }
        }

        canvas.addEventListener('mousedown', (e) => {
            const intersects = pickHandle(e);
            if (intersects.length > 0) {
                isDragging = true;
                dragTarget = intersects[0].object;
                dragTarget.material.emissiveIntensity = 1.0;
                dragTarget.scale.setScalar(1.3);
                dragStartMouse.copy(mouse);
                dragStartDistance = distanceFactor;
                canvas.style.cursor = 'grabbing';
            }
        });
        canvas.addEventListener('mousemove', moveByMouse);
        const onMouseUp = () => {
            if (dragTarget) {
                dragTarget.material.emissiveIntensity = 0.5;
                dragTarget.scale.setScalar(1);
                const targetAz = snapToNearest(azimuthAngle, azimuthSteps);
                const targetEl = snapToNearest(elevationAngle, elevationSteps);
                const startAz = azimuthAngle, startEl = elevationAngle;
                const startTime = Date.now();
                function animateSnap() {
                    const t = Math.min((Date.now() - startTime) / 200, 1);
                    const ease = 1 - Math.pow(1 - t, 3);
                    let azDiff = targetAz - startAz;
                    if (azDiff > 180) azDiff -= 360;
                    if (azDiff < -180) azDiff += 360;
                    azimuthAngle = startAz + azDiff * ease;
                    if (azimuthAngle < 0) azimuthAngle += 360;
                    if (azimuthAngle >= 360) azimuthAngle -= 360;
                    elevationAngle = startEl + (targetEl - startEl) * ease;
                    updatePositions();
                    if (t < 1) requestAnimationFrame(animateSnap);
                    else updatePropsAndTrigger();
                }
                animateSnap();
            }
            isDragging = false; dragTarget = null; canvas.style.cursor = 'default';
        };
        canvas.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('mouseleave', onMouseUp);

        canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            const intersects = pickHandle(e);
            if (intersects.length > 0) {
                isDragging = true; dragTarget = intersects[0].object;
                dragTarget.material.emissiveIntensity = 1.0;
                dragTarget.scale.setScalar(1.3);
                dragStartMouse.copy(mouse);
                dragStartDistance = distanceFactor;
            }
        }, { passive: false });
        canvas.addEventListener('touchmove', (e) => { e.preventDefault(); moveByMouse(e); }, { passive: false });
        canvas.addEventListener('touchend', (e) => { e.preventDefault(); onMouseUp(); }, { passive: false });
        canvas.addEventListener('touchcancel', (e) => { e.preventDefault(); onMouseUp(); }, { passive: false });

        updatePositions();

        function render() {
            requestAnimationFrame(render);
            renderer.render(scene, camera);
        }
        render();

        new ResizeObserver(() => {
            camera.aspect = wrapper.clientWidth / wrapper.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(wrapper.clientWidth, wrapper.clientHeight);
        }).observe(wrapper);

        wrapper._updateFromProps = (newVal) => {
            if (newVal && typeof newVal === 'object') {
                azimuthAngle = newVal.azimuth ?? azimuthAngle;
                elevationAngle = newVal.elevation ?? elevationAngle;
                distanceFactor = newVal.distance ?? distanceFactor;
                updatePositions();
            }
        };
        wrapper._updateTexture = updateTextureFromUrl;
        wrapper._resetCamera = () => {
            azimuthAngle = 0; elevationAngle = 0; distanceFactor = 1.0;
            updatePositions();
            updatePropsAndTrigger();
        };

        let lastImageUrl = props.imageUrl;
        let lastValue = JSON.stringify(props.value);
        setInterval(() => {
            if (props.imageUrl !== lastImageUrl) {
                lastImageUrl = props.imageUrl;
                updateTextureFromUrl(props.imageUrl);
            }
            const currentValue = JSON.stringify(props.value);
            if (currentValue !== lastValue) {
                lastValue = currentValue;
                if (props.value && typeof props.value === 'object') {
                    azimuthAngle = props.value.azimuth ?? azimuthAngle;
                    elevationAngle = props.value.elevation ?? elevationAngle;
                    distanceFactor = props.value.distance ?? distanceFactor;
                    updatePositions();
                }
            }
        }, 100);
    };
    initScene();
})();
"""


def build_camera_3d_html_template():
    """3D 控件的 HTML 模板（含 prompt 浮层 + 角度读数）。"""
    return """
    <div id="camera-control-wrapper" style="width: 100%; height: 450px; position: relative; background: #1a1a1a; border-radius: 12px; overflow: hidden;">
        <div id="angle-readout" style="position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); padding: 6px 10px; border-radius: 6px; font-family: monospace; font-size: 11px; color: #aaa; z-index: 10;">Az 0°  El 0°  D 1.00</div>
        <div id="prompt-overlay" style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.8); padding: 8px 16px; border-radius: 8px; font-family: monospace; font-size: 12px; color: #00ff88; white-space: nowrap; z-index: 10;"></div>
    </div>
    """


class CameraControl3D(gr.HTML):
    """基于 Three.js 的 3D 相机控制器组件。"""

    def __init__(self, value=None, imageUrl=None, **kwargs):
        if value is None:
            value = {"azimuth": 0, "elevation": 0, "distance": 1.0}
        super().__init__(
            value=value,
            html_template=build_camera_3d_html_template(),
            js_on_load=CAMERA_3D_JS,
            imageUrl=imageUrl,
            **kwargs
        )


# ====================== 全局样式 ======================
BASE_CSS = """
#col-container { max-width: 1280px; margin: 0 auto; }
.dark .progress-text { color: white !important; }
#camera-3d-control { min-height: 450px; }
.slider-row { display: flex; gap: 10px; align-items: center; }
.preset-btn { min-width: 80px !important; }
.hero-title { text-align: center; padding: 12px 0 4px; }
.hero-badges { text-align: center; margin-bottom: 8px; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; margin: 0 4px; }
.badge-blue { background: #e0ecff; color: #1a4fa0; }
.badge-green { background: #e3f7e8; color: #137a3b; }
.badge-purple { background: #f0e7ff; color: #5a2da0; }
.dark .badge-blue { background: #1a2f50; color: #7eb0ff; }
.dark .badge-green { background: #1a3a26; color: #6ee39a; }
.dark .badge-purple { background: #2e1a4a; color: #c89dff; }
.foot-note { text-align: center; color: #888; font-size: 12px; margin-top: 16px; }
.info-card { background: rgba(0, 116, 217, 0.06); border: 1px solid rgba(0, 116, 217, 0.2); border-radius: 8px; padding: 10px 14px !important; font-size: 13px; line-height: 1.6; flex: 1; overflow: auto; max-height: 130px; }
.dark .info-card { background: rgba(100, 160, 255, 0.08); border-color: rgba(100, 160, 255, 0.25); }
"""


def combined_css():
    return BASE_CSS + ' .fillable{max-width: 1280px !important} footer{display:none !important}'


def image_to_data_url(image):
    """供 sync_3d_image 使用的工具：PIL 图 → data URL。"""
    if image is None:
        return None
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"
