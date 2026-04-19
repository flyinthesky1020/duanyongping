/* 3D Word Cloud — Three.js */

let wcScene, wcCamera, wcRenderer, wcControls;
let wcSprites = [];
let wcAnimId = null;
let wcRaycaster, wcMouse;
let wcHovered = null;
const WC_SPHERE_RADIUS = 130;
const WC_SPRITE_SCALE = 1.05;
const WC_MIN_WEIGHT = 20;
const WC_MAX_WEIGHT = 95;

function initWordCloud(words) {
  const canvas = document.getElementById("wordcloud-canvas");
  const wrap = document.getElementById("wordcloud-wrap");
  if (!canvas || !wrap || typeof THREE === "undefined") {
    throw new Error("Three.js word cloud dependencies are unavailable");
  }

  disposeWordCloud();

  const W = wrap.clientWidth;
  const H = wrap.clientHeight;

  // Scene
  wcScene = new THREE.Scene();

  // Camera
  wcCamera = new THREE.PerspectiveCamera(60, W / H, 0.1, 2000);
  wcCamera.position.set(0, 26, 500);

  // Renderer
  wcRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  wcRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  wcRenderer.setSize(W, H);
  wcRenderer.setClearColor(0x000000, 1);

  // Stars background
  _addStars();

  // OrbitControls CDN path used by the previous version was removed upstream.
  // Keep the cloud interactive without taking a hard dependency on that addon.
  wcControls = null;

  // Raycaster
  wcRaycaster = new THREE.Raycaster();
  wcMouse = new THREE.Vector2(-9999, -9999);

  // Build sprites
  _buildSprites(words);

  // Events
  canvas.addEventListener("mousemove", _onMouseMove);
  canvas.addEventListener("click", _onClick);
  window.addEventListener("resize", _onResize);

  // Start loop
  _animate();
}

function _addStars() {
  const geo = new THREE.BufferGeometry();
  const count = 800;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count * 3; i++) {
    positions[i] = (Math.random() - 0.5) * 3000;
  }
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const mat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.8, transparent: true, opacity: 0.4 });
  wcScene.add(new THREE.Points(geo, mat));
}

function _buildSprites(words) {
  // Fibonacci sphere placement
  const n = words.length;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const radius = WC_SPHERE_RADIUS;

  words.forEach((word, i) => {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * r;
    const z = Math.sin(theta) * r;

    const sprite = _makeTextSprite(word);
    sprite.position.set(x * radius, y * radius, z * radius);
    wcScene.add(sprite);
    wcSprites.push(sprite);
  });
}

function _makeTextSprite(word) {
  const { text, weight, type } = word;
  const dpr = Math.min(window.devicePixelRatio, 2);

  // Font size: map weight 20-95 → 10-28px
  const clampedWeight = Math.max(WC_MIN_WEIGHT, Math.min(WC_MAX_WEIGHT, weight || WC_MIN_WEIGHT));
  const normalizedWeight = (clampedWeight - WC_MIN_WEIGHT) / (WC_MAX_WEIGHT - WC_MIN_WEIGHT);
  const fontSize = Math.round(10 + normalizedWeight * 18);
  const font = `bold ${fontSize * dpr}px "PingFang SC", "Microsoft YaHei", sans-serif`;

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  ctx.font = font;
  const textW = ctx.measureText(text).width + 20 * dpr;
  const textH = (fontSize + 12) * dpr;
  canvas.width = textW;
  canvas.height = textH;

  ctx.font = font;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Color by type
  let color;
  if (type === "concept") color = "#e8d5a3";
  else if (type === "stock") color = "#4ade80";
  else color = "#93c5fd";

  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
  });
  const sprite = new THREE.Sprite(material);

  // Scale: world units corresponding to pixel size at radius 260
  const maxSpriteWidth = Math.min(window.innerWidth * 0.28, 180);
  const unclampedScaleX = (textW / dpr) * WC_SPRITE_SCALE;
  const scaleX = Math.min(unclampedScaleX, maxSpriteWidth);
  const scaleY = (textH / dpr) * WC_SPRITE_SCALE;
  sprite.scale.set(scaleX, scaleY, 1);

  // Store metadata
  sprite.userData = { word };

  return sprite;
}

function _onMouseMove(e) {
  const rect = wcRenderer.domElement.getBoundingClientRect();
  wcMouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  wcMouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  wcRaycaster.setFromCamera(wcMouse, wcCamera);
  const hits = wcRaycaster.intersectObjects(wcSprites);

  if (hits.length > 0) {
    const sprite = hits[0].object;
    if (wcHovered !== sprite) {
      if (wcHovered) wcHovered.material.opacity = 1;
      wcHovered = sprite;
      wcHovered.material.opacity = 0.85;
      wcRenderer.domElement.style.cursor = "pointer";
    }
  } else {
    if (wcHovered) {
      wcHovered.material.opacity = 1;
      wcHovered = null;
    }
    wcRenderer.domElement.style.cursor = "default";
  }
}

function _onClick(e) {
  if (!wcHovered) return;
  const { word } = wcHovered.userData;
  if (word && word.target) {
    window.navigateFromWordcloud(word.target);
  }
}

function _onResize() {
  const wrap = document.getElementById("wordcloud-wrap");
  if (!wrap || !wcCamera || !wcRenderer) return;
  const W = wrap.clientWidth;
  const H = wrap.clientHeight;
  wcCamera.aspect = W / H;
  wcCamera.updateProjectionMatrix();
  wcRenderer.setSize(W, H);
}

function _animate() {
  wcAnimId = requestAnimationFrame(_animate);

  if (wcScene) {
    wcScene.rotation.y += 0.0015;
  }

  // Depth fade: update opacity based on z distance from camera
  if (wcSprites.length > 0) {
    wcSprites.forEach(sprite => {
      const pos = sprite.position.clone().applyMatrix4(wcCamera.matrixWorldInverse);
      // z ranges roughly -260 to +260 in camera space; map to 0.25-1.0
      const depth = (pos.z + 300) / 600;
      const opacity = Math.max(0.2, Math.min(1.0, depth * 0.9));
      if (sprite !== wcHovered) {
        sprite.material.opacity = opacity;
      }
    });
  }

  if (wcControls) wcControls.update();
  wcRenderer.render(wcScene, wcCamera);
}

function disposeWordCloud() {
  if (wcAnimId) {
    cancelAnimationFrame(wcAnimId);
    wcAnimId = null;
  }

  const canvas = document.getElementById("wordcloud-canvas");
  if (canvas) {
    canvas.removeEventListener("mousemove", _onMouseMove);
    canvas.removeEventListener("click", _onClick);
  }
  window.removeEventListener("resize", _onResize);

  wcSprites.forEach(sprite => {
    if (sprite.material && sprite.material.map) sprite.material.map.dispose();
    if (sprite.material) sprite.material.dispose();
    if (wcScene) wcScene.remove(sprite);
  });

  wcSprites = [];
  wcHovered = null;

  if (wcRenderer) {
    wcRenderer.dispose();
  }

  wcScene = null;
  wcCamera = null;
  wcRenderer = null;
  wcControls = null;
  wcRaycaster = null;
  wcMouse = null;
}
