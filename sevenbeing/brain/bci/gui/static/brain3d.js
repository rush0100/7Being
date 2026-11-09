/* Segmented 3D brain for 7Being.
   Sulcus / pathway streaks; color mass in each lobe matches band share %. */
(function (global) {
  "use strict";

  const BANDS = ["delta", "theta", "alpha", "beta", "gamma"];
  const BAND_HEX = {
    delta: 0x6b7f86,
    theta: 0x7eb6ff,
    alpha: 0x3ecf8e,
    beta: 0xf0b35a,
    gamma: 0xc4a0ff,
  };
  const BAND_RGB = BANDS.map((name) => {
    const h = BAND_HEX[name];
    return [(h >> 16) & 255, (h >> 8) & 255, h & 255];
  });
  const IDLE = 0x3a4e56;
  const FIBERS_PER_PART = 80;
  const SEGS = 16;

  const PARTS = [
    { id: "frontal_L", lobe: "frontal", channels: ["AF3", "F7", "F3", "FC5"],
      cx: -0.38, cy: 0.42, cz: 0.62, sx: 0.62, sy: 0.52, sz: 0.55, rx: 0.18, ry: -0.35, rz: 0.1 },
    { id: "frontal_R", lobe: "frontal", channels: ["AF4", "F8", "F4", "FC6"],
      cx: 0.38, cy: 0.42, cz: 0.62, sx: 0.62, sy: 0.52, sz: 0.55, rx: 0.18, ry: 0.35, rz: -0.1 },
    { id: "temporal_L", lobe: "temporal", channels: ["T7"],
      cx: -0.78, cy: -0.05, cz: 0.05, sx: 0.38, sy: 0.42, sz: 0.55, rx: 0.25, ry: -0.55, rz: 0.15 },
    { id: "temporal_R", lobe: "temporal", channels: ["T8"],
      cx: 0.78, cy: -0.05, cz: 0.05, sx: 0.38, sy: 0.42, sz: 0.55, rx: 0.25, ry: 0.55, rz: -0.15 },
    { id: "parietal_L", lobe: "parietal", channels: ["P7"],
      cx: -0.42, cy: 0.28, cz: -0.42, sx: 0.55, sy: 0.48, sz: 0.5, rx: -0.2, ry: -0.25, rz: 0.08 },
    { id: "parietal_R", lobe: "parietal", channels: ["P8"],
      cx: 0.42, cy: 0.28, cz: -0.42, sx: 0.55, sy: 0.48, sz: 0.5, rx: -0.2, ry: 0.25, rz: -0.08 },
    { id: "occipital_L", lobe: "occipital", channels: ["O1"],
      cx: -0.28, cy: 0.05, cz: -0.78, sx: 0.45, sy: 0.42, sz: 0.4, rx: -0.35, ry: -0.15, rz: 0.05 },
    { id: "occipital_R", lobe: "occipital", channels: ["O2"],
      cx: 0.28, cy: 0.05, cz: -0.78, sx: 0.45, sy: 0.42, sz: 0.4, rx: -0.35, ry: 0.15, rz: -0.05 },
  ];

  const SPOTS_3D = {
    AF3: [-0.32, 0.72, 0.72], F7: [-0.72, 0.35, 0.55], F3: [-0.38, 0.62, 0.55],
    FC5: [-0.62, 0.22, 0.32], T7: [-0.92, -0.05, 0.0], P7: [-0.68, 0.05, -0.55],
    O1: [-0.28, -0.05, -0.92], O2: [0.28, -0.05, -0.92], P8: [0.68, 0.05, -0.55],
    T8: [0.92, -0.05, 0.0], FC6: [0.62, 0.22, 0.32], F4: [0.38, 0.62, 0.55],
    F8: [0.72, 0.35, 0.55], AF4: [0.32, 0.72, 0.72],
  };

  function hash(n) {
    const x = Math.sin(n * 127.1) * 43758.5453;
    return x - Math.floor(x);
  }

  function deformPoint(v, part) {
    const fissure = 1 - 0.12 * Math.exp(-((v.x * 4) ** 2));
    const gyrus = 1 + 0.045 * Math.sin(v.x * 9 + v.z * 7) * Math.cos(v.y * 8);
    const tip = 1 + 0.08 * Math.max(0, v.z) * (part.lobe === "frontal" ? 1 : 0.3);
    v.multiplyScalar(fissure * gyrus * tip * 0.92);
    return v;
  }

  function makeLobeGeometry(part) {
    const geo = new THREE.SphereGeometry(1, 28, 22);
    const pos = geo.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      deformPoint(v, part);
      pos.setXYZ(i, v.x, v.y, v.z);
    }
    pos.needsUpdate = true;
    geo.computeVertexNormals();
    return geo;
  }

  function fiberPoints(part, fiberIndex) {
    const seed = hash(fiberIndex * 17.13 + part.id.length * 3.7);
    const seed2 = hash(fiberIndex * 91.7 + 2.3);
    const seed3 = hash(fiberIndex * 3.1 + 8.8);
    let theta = seed * Math.PI;
    let phi = seed2 * Math.PI * 2;
    const dTheta = (0.035 + seed3 * 0.05) * (seed > 0.5 ? 1 : -1);
    const dPhi = (0.055 + seed * 0.07) * (seed2 > 0.5 ? 1 : -1);
    const mode = fiberIndex % 3;
    const pts = [];
    const v = new THREE.Vector3();
    for (let s = 0; s <= SEGS; s++) {
      const t = s / SEGS;
      let th = theta + dTheta * s;
      let ph = phi + dPhi * s;
      if (mode === 0) {
        th = 0.35 + seed * 2.2 + 0.55 * Math.sin(ph * 2.2);
        ph = phi + (t - 0.5) * 2.4;
      } else if (mode === 1) {
        th = theta + (t - 0.5) * 1.6;
        ph = phi + 0.9 * Math.sin(th * 3.0 + seed);
      } else {
        th = theta + 0.45 * Math.sin(s * 0.55 + seed2 * 6);
        ph = phi + dPhi * s * 1.15;
      }
      const r = 1.02 + 0.02 * Math.sin(s * 1.7 + seed3 * 10);
      v.set(
        r * Math.sin(th) * Math.cos(ph),
        r * Math.cos(th),
        r * Math.sin(th) * Math.sin(ph)
      );
      deformPoint(v, part);
      pts.push(v.x, v.y, v.z);
    }
    return pts;
  }

  /** One geometry: all sulcus fibers + per-vertex RGB (updated to match share). */
  function makePathwayGeometry(part) {
    const positions = [];
    const colors = [];
    for (let f = 0; f < FIBERS_PER_PART; f++) {
      const pts = fiberPoints(part, f);
      for (let s = 0; s < SEGS; s++) {
        const i = s * 3;
        const j = (s + 1) * 3;
        positions.push(pts[i], pts[i + 1], pts[i + 2], pts[j], pts[j + 1], pts[j + 2]);
        // placeholder grey; rewritten every update()
        colors.push(0.25, 0.32, 0.36, 0.25, 0.32, 0.36);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.userData = {
      fiberCount: FIBERS_PER_PART,
      segsPerFiber: SEGS,
      vertsPerFiber: SEGS * 2,
    };
    return geo;
  }

  /** Split fiber indices so counts[b] / N ≈ share[b] (largest remainder). */
  function allocateFibers(share, nFibers) {
    const raw = share.map((v) => Math.max(0, v || 0));
    const sum = raw.reduce((a, b) => a + b, 0) || 1;
    const exact = raw.map((v) => (v / sum) * nFibers);
    const counts = exact.map((v) => Math.floor(v));
    let used = counts.reduce((a, b) => a + b, 0);
    const order = exact
      .map((v, i) => ({ i, frac: v - Math.floor(v) }))
      .sort((a, b) => b.frac - a.frac);
    let k = 0;
    while (used < nFibers && k < order.length * 2) {
      counts[order[k % order.length].i] += 1;
      used += 1;
      k += 1;
    }
    return counts;
  }

  function paintPathwayColors(geo, share) {
    const colorAttr = geo.attributes.color;
    const arr = colorAttr.array;
    const { fiberCount, segsPerFiber, vertsPerFiber } = geo.userData;
    const counts = allocateFibers(share, fiberCount);
    let fiber = 0;
    for (let b = 0; b < BANDS.length; b++) {
      const [r, g, bl] = BAND_RGB[b];
      const rf = r / 255;
      const gf = g / 255;
      const bf = bl / 255;
      const n = counts[b];
      for (let f = 0; f < n; f++, fiber++) {
        const base = fiber * vertsPerFiber * 3;
        for (let v = 0; v < vertsPerFiber; v++) {
          const o = base + v * 3;
          arr[o] = rf;
          arr[o + 1] = gf;
          arr[o + 2] = bf;
        }
      }
    }
    // Any leftover (rounding) → idle
    while (fiber < fiberCount) {
      const base = fiber * vertsPerFiber * 3;
      for (let v = 0; v < vertsPerFiber; v++) {
        const o = base + v * 3;
        arr[o] = 0.22;
        arr[o + 1] = 0.28;
        arr[o + 2] = 0.32;
      }
      fiber += 1;
    }
    colorAttr.needsUpdate = true;
    return counts;
  }

  function meanShare(rows, lobeFallback) {
    if (rows && rows.length) {
      const n = rows[0].share.length;
      const out = new Array(n).fill(0);
      for (const row of rows) {
        for (let i = 0; i < n; i++) out[i] += row.share[i] || 0;
      }
      for (let i = 0; i < n; i++) out[i] /= rows.length;
      return out;
    }
    if (lobeFallback && lobeFallback.share) return lobeFallback.share.slice();
    return BANDS.map(() => 0);
  }

  function Brain3D(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
      powerPreference: "low-power",
    });
    this.renderer.setClearColor(0x07141c, 1);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 40);
    this.camera.position.set(0, 1.6, 4.2);
    this.camera.lookAt(0, 0.1, 0);

    const amb = new THREE.AmbientLight(0xd0e8f0, 0.7);
    const key = new THREE.DirectionalLight(0xffffff, 0.95);
    key.position.set(2.4, 3.2, 2.8);
    const fill = new THREE.DirectionalLight(0x6ec8ff, 0.4);
    fill.position.set(-2.2, 0.4, -1.5);
    this.scene.add(amb, key, fill);

    this.root = new THREE.Group();
    this.root.rotation.x = -0.18;
    this.root.scale.setScalar(1.15);
    this.scene.add(this.root);

    const shellMat = new THREE.MeshStandardMaterial({
      color: 0x1c2c34,
      roughness: 0.7,
      metalness: 0.02,
      transparent: true,
      opacity: 0.16,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const shell = new THREE.Mesh(new THREE.SphereGeometry(1.15, 40, 28), shellMat);
    shell.scale.set(1.05, 0.95, 1.25);
    shell.position.y = 0.08;
    this.root.add(shell);

    const mid = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.7, 1.5),
      new THREE.MeshStandardMaterial({ color: 0x0d181e, transparent: true, opacity: 0.3 })
    );
    mid.position.set(0, 0.15, 0.05);
    this.root.add(mid);

    this.parts = {};
    for (const part of PARTS) {
      const group = new THREE.Group();
      group.position.set(part.cx, part.cy, part.cz);
      group.scale.set(part.sx, part.sy, part.sz);
      group.rotation.set(part.rx, part.ry, part.rz);

      const shellMesh = new THREE.Mesh(
        makeLobeGeometry(part),
        new THREE.MeshStandardMaterial({
          color: IDLE,
          roughness: 0.55,
          metalness: 0.04,
          transparent: true,
          opacity: 0.22,
          depthWrite: false,
        })
      );
      group.add(shellMesh);

      const edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(shellMesh.geometry, 26),
        new THREE.LineBasicMaterial({ color: 0x6fd6c8, transparent: true, opacity: 0.12 })
      );
      group.add(edge);

      const pathwayGeo = makePathwayGeometry(part);
      const pathwayMat = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.92,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const pathway = new THREE.LineSegments(pathwayGeo, pathwayMat);
      pathway.renderOrder = 2;
      group.add(pathway);

      group.userData = {
        part,
        share: BANDS.map(() => 0),
        counts: BANDS.map(() => 0),
        pathway,
        pathwayGeo,
        pathwayMat,
        shell: shellMesh,
      };
      this.root.add(group);
      this.parts[part.id] = group;
    }

    this.spots = {};
    const spotGeo = new THREE.SphereGeometry(0.05, 12, 10);
    for (const [name, xyz] of Object.entries(SPOTS_3D)) {
      const mat = new THREE.MeshStandardMaterial({
        color: 0x243840,
        emissive: 0x000000,
        emissiveIntensity: 0,
        roughness: 0.35,
      });
      const mesh = new THREE.Mesh(spotGeo, mat);
      mesh.position.set(xyz[0], xyz[1], xyz[2]);
      this.root.add(mesh);
      const rings = BANDS.map((band) => {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.06, 0.09, 20),
          new THREE.MeshBasicMaterial({
            color: BAND_HEX[band],
            transparent: true,
            opacity: 0,
            side: THREE.DoubleSide,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          })
        );
        ring.position.copy(mesh.position);
        ring.lookAt(0, 0.1, 0);
        this.root.add(ring);
        return ring;
      });
      this.spots[name] = { mesh, mat, share: BANDS.map(() => 0), rings };
    }

    this.drag = { active: false, x: 0, y: 0 };
    this.yaw = 0.55;
    this.pitch = 0.35;
    this.distance = 4.2;
    this.view = "free";
    this._applyCamera();

    canvas.addEventListener("pointerdown", (ev) => {
      this.drag.active = true;
      this.drag.x = ev.clientX;
      this.drag.y = ev.clientY;
      canvas.setPointerCapture(ev.pointerId);
      this.view = "free";
    });
    canvas.addEventListener("pointerup", () => { this.drag.active = false; });
    canvas.addEventListener("pointercancel", () => { this.drag.active = false; });
    canvas.addEventListener("pointermove", (ev) => {
      if (!this.drag.active) return;
      const dx = ev.clientX - this.drag.x;
      const dy = ev.clientY - this.drag.y;
      this.drag.x = ev.clientX;
      this.drag.y = ev.clientY;
      this.yaw -= dx * 0.008;
      this.pitch = Math.max(-0.85, Math.min(1.15, this.pitch + dy * 0.008));
      this._applyCamera();
    });
    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      this.distance = Math.max(2.4, Math.min(7.5, this.distance + ev.deltaY * 0.004));
      this.view = "free";
      this._applyCamera();
    }, { passive: false });

    this._raf = 0;
    this._tick = this._tick.bind(this);
    this.resize();
    this._raf = requestAnimationFrame(this._tick);
  }

  Brain3D.prototype._applyCamera = function () {
    const c = Math.cos(this.pitch);
    this.camera.position.set(
      Math.sin(this.yaw) * c * this.distance,
      Math.sin(this.pitch) * this.distance * 0.85 + 0.35,
      Math.cos(this.yaw) * c * this.distance
    );
    this.camera.lookAt(0, 0.12, 0.05);
  };

  Brain3D.prototype.setView = function (mode) {
    this.view = mode;
    if (mode === "top") {
      this.yaw = 0;
      this.pitch = 1.12;
      this.distance = 4.0;
    } else if (mode === "side") {
      this.yaw = Math.PI * 0.5;
      this.pitch = 0.18;
      this.distance = 4.4;
    } else if (mode === "front") {
      this.yaw = 0;
      this.pitch = 0.22;
      this.distance = 4.3;
    }
    this._applyCamera();
  };

  Brain3D.prototype.resize = function () {
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.renderer.setSize(w, h, false);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    }
  };

  Brain3D.prototype.update = function (data) {
    if (!data) return;
    const byName = {};
    for (const ch of data.channels || []) byName[ch.name] = ch;
    const lobeByName = {};
    for (const lobe of data.lobes || []) lobeByName[lobe.name] = lobe;

    for (const group of Object.values(this.parts)) {
      const part = group.userData.part;
      const rows = part.channels.map((n) => byName[n]).filter(Boolean);
      const share = meanShare(rows, lobeByName[part.lobe]);
      group.userData.share = share;
      group.userData.counts = paintPathwayColors(group.userData.pathwayGeo, share);
      const peak = Math.max(0, ...share);
      group.userData.shell.material.opacity = 0.14 + peak * 0.1;
      // Dim pathways slightly when overall power is flat/low
      group.userData.pathwayMat.opacity = 0.35 + peak * 0.65;
    }

    for (const [name, spot] of Object.entries(this.spots)) {
      const row = byName[name];
      if (!row) continue;
      spot.share = row.share || spot.share;
      const c = new THREE.Color(0x000000);
      let wsum = 0;
      for (let b = 0; b < BANDS.length; b++) {
        const w = Math.max(0, spot.share[b] || 0);
        if (w <= 0) continue;
        c.r += BAND_RGB[b][0] / 255 * w;
        c.g += BAND_RGB[b][1] / 255 * w;
        c.b += BAND_RGB[b][2] / 255 * w;
        wsum += w;
      }
      if (wsum > 0) c.multiplyScalar(1 / wsum);
      else c.setHex(IDLE);
      spot.mat.color.copy(c);
      spot.mat.emissive.copy(c);
      const peak = Math.max(0, ...spot.share);
      spot.mat.emissiveIntensity = 0.15 + peak * 0.85;
      spot.mesh.scale.setScalar(0.85 + peak * 0.45);
      // Ring arc length ≈ share (opacity * angular scale via scale.x asymmetry not available;
      // use opacity proportional to share, thickness via scale).
      for (let b = 0; b < BANDS.length; b++) {
        const v = Math.max(0, spot.share[b] || 0);
        spot.rings[b].material.opacity = v;
        spot.rings[b].scale.setScalar(0.85 + b * 0.2 + v * 0.55);
      }
    }
  };

  Brain3D.prototype._tick = function (ts) {
    this._raf = requestAnimationFrame(this._tick);
    this.resize();
    const t = ts * 0.001;
    if (!this.drag.active && this.view === "free") {
      this.yaw += 0.0012;
      this._applyCamera();
    }
    for (const group of Object.values(this.parts)) {
      const share = group.userData.share || [];
      const peak = Math.max(0, ...share);
      const base = group.userData.part;
      const breathe = 1 + peak * 0.025 * Math.sin(t * 2.6 + base.cx);
      group.scale.set(base.sx * breathe, base.sy * breathe, base.sz * breathe);
      group.userData.pathway.rotation.y = Math.sin(t * 0.35) * 0.015 * (peak > 0.2 ? 1 : 0);
    }
    for (const spot of Object.values(this.spots)) {
      for (let b = 0; b < spot.rings.length; b++) {
        spot.rings[b].rotation.z = t * (0.35 + b * 0.12);
      }
    }
    this.renderer.render(this.scene, this.camera);
  };

  Brain3D.prototype.destroy = function () {
    cancelAnimationFrame(this._raf);
    this.renderer.dispose();
  };

  global.Brain3D = Brain3D;
  global.BRAIN3D_PARTS = PARTS;
  global.BRAIN3D_BANDS = BANDS;
})(typeof window !== "undefined" ? window : globalThis);
