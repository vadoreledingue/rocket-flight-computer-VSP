class Rocket3D {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      throw new Error(`Container #${containerId} not found`);
    }

    // Verify Three.js is available
    if (typeof THREE === "undefined") {
      throw new Error("Three.js library not loaded");
    }

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.rocketMesh = null;
    this.arrows = { x: null, y: null, z: null };
    this.animationFrameId = null;
    this.initialized = false;

    try {
      this._init();
      this.initialized = true;
    } catch (e) {
      console.error("[ROCKET3D] Initialization failed:", e);
      throw e;
    }
  }

  _init() {
    // Scene setup
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a1628); // Match dashboard dark theme

    // Camera setup: isometric-ish view
    let width = this.container.clientWidth || 300;
    let height = this.container.clientHeight || 300;

    if (width === 0) width = 300;
    if (height === 0) height = 300;

    const fov = 50;
    this.camera = new THREE.PerspectiveCamera(fov, width / height, 0.1, 1000);
    this.camera.position.set(2, 2, 2);
    this.camera.lookAt(0, 0, 0);

    // Renderer setup with WebGL 1.0 support
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    } catch (e) {
      this.renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
    }
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowShadowMap;
    this.container.appendChild(this.renderer.domElement);

    // Rocket mesh: rectangular prism (L:W:H = 2:0.5:0.3 ratio)
    const rocketGeometry = new THREE.BoxGeometry(2, 0.5, 0.3);
    const rocketMaterial = new THREE.MeshPhongMaterial({
      color: 0x00ccff, // Cyan to match dashboard
      emissive: 0x003366,
      shininess: 100,
      flatShading: false,
    });
    this.rocketMesh = new THREE.Mesh(rocketGeometry, rocketMaterial);
    this.rocketMesh.castShadow = true;
    this.rocketMesh.receiveShadow = true;
    this.rocketMesh.rotation.order = "YXZ"; // Yaw, Pitch, Roll order
    this.scene.add(this.rocketMesh);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(3, 4, 3);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 512;
    directionalLight.shadow.mapSize.height = 512;
    this.scene.add(directionalLight);

    // Initialize arrows (acceleration indicators)
    this._initArrows();

    // Handle window resize
    window.addEventListener("resize", () => this._onWindowResize());

    // Handle WebGL context loss
    this.renderer.domElement.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      console.warn("[ROCKET3D] WebGL context lost");
      this.initialized = false;
    });

    // Start render loop
    this._animate();
  }

  _initArrows() {
    const arrowLength = 0.5;
    const arrowHeadSize = 0.15;

    // X-axis arrow (red)
    this.arrows.x = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 0, 0),
      arrowLength,
      0xff0000,
      arrowHeadSize,
      arrowHeadSize * 0.6,
    );
    this.arrows.x.visible = false;
    this.rocketMesh.add(this.arrows.x);

    // Y-axis arrow (green)
    this.arrows.y = new THREE.ArrowHelper(
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, 0, 0),
      arrowLength,
      0x00ff00,
      arrowHeadSize,
      arrowHeadSize * 0.6,
    );
    this.arrows.y.visible = false;
    this.rocketMesh.add(this.arrows.y);

    // Z-axis arrow (blue)
    this.arrows.z = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(0, 0, 0),
      arrowLength,
      0x0000ff,
      arrowHeadSize,
      arrowHeadSize * 0.6,
    );
    this.arrows.z.visible = false;
    this.rocketMesh.add(this.arrows.z);
  }

  update(roll, pitch, yaw) {
    if (!this.initialized) return;

    // Convert degrees to radians
    const rollRad = roll * (Math.PI / 180);
    const pitchRad = pitch * (Math.PI / 180);
    const yawRad = yaw * (Math.PI / 180);

    // Apply rotation (Euler order: YXZ for yaw-pitch-roll)
    this.rocketMesh.rotation.y = yawRad;
    this.rocketMesh.rotation.x = pitchRad;
    this.rocketMesh.rotation.z = rollRad;
  }

  updateAcceleration(accelX, accelY, accelZ) {
    if (!this.initialized) return;

    // Calculate magnitudes (m/s²)
    const magX = Math.abs(accelX);
    const magY = Math.abs(accelY);
    const magZ = Math.abs(accelZ);

    // Scale factor: arrow length proportional to acceleration
    // 20 m/s² (2g) → arrow length of 1.0
    const scaleFactor = 0.5;
    const maxArrowLen = 2.0;

    this._updateArrow("x", accelX, magX * scaleFactor, maxArrowLen);
    this._updateArrow("y", accelY, magY * scaleFactor, maxArrowLen);
    this._updateArrow("z", accelZ, magZ * scaleFactor, maxArrowLen);
  }

  _updateArrow(axis, accelValue, length, maxLen) {
    const arrow = this.arrows[axis];
    if (!arrow) return;

    // Clamp length
    length = Math.min(Math.max(length, 0), maxLen);

    // Show arrow only if acceleration is significant (> 0.3 m/s²)
    const threshold = 0.3;
    if (Math.abs(accelValue) < threshold) {
      arrow.visible = false;
      return;
    }

    arrow.visible = true;

    // Simple: just scale the arrow based on magnitude
    const scale = Math.max(0.2, Math.min(length, maxLen));
    arrow.scale.set(scale, scale, scale);
  }

  _animate() {
    this.animationFrameId = requestAnimationFrame(() => this._animate());
    this.renderer.render(this.scene, this.camera);
  }

  _onWindowResize() {
    if (!this.renderer || !this.camera) return;

    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.renderer && this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
    this.initialized = false;
  }

  getStatus() {
    return {
      initialized: this.initialized,
      hasWebGL:
        (!!this.renderer && !!this.renderer.capabilities.isWebGL2) ||
        !!this.renderer.capabilities.isWebGL,
      containerSize: {
        width: this.container.clientWidth,
        height: this.container.clientHeight,
      },
    };
  }
}
