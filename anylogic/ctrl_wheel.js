/* Presentation-only input for the native AnyLogic 3D canvas. */
(() => {
  if (window.__maritimeViewControls) return;
  const state = {factor: 1, min: .25, max: 4, wheelEvents: 0, installed: true, version: 2, pan: [0, 0, 0], panEvents: 0};
  window.__maritimeViewControls = state;
  const active = () => {
    const world = window.AnimationSVG?.client?.frameDrawing?.world3d;
    return world?.canvases3d?.filter(c => c._visible && c.active).slice(-1)[0];
  };
  let badge, dragging = false, applying = false;
  const attached = new WeakSet();
  function translate(view, direction) {
    const p = view.camera.position, t = view.controls.target;
    p.x += direction * state.pan[0]; p.y += direction * state.pan[1]; p.z += direction * state.pan[2];
    t.x += direction * state.pan[0]; t.y += direction * state.pan[1]; t.z += direction * state.pan[2];
  }
  function attachPan(view) {
    if (!view?.controls) return;
    const controls = view.controls;
    // Reuse the bundled OrbitControls pan, keeping left-button rotation.
    controls.enablePan = true;
    controls.mouseButtons.PAN = 1;
    controls.mouseButtons.ZOOM = -1;
    if (attached.has(view)) return;
    attached.add(view);
    let lastTarget = controls.target.clone();
    controls.addEventListener('change', () => {
      if (dragging && !applying) {
        state.pan[0] += controls.target.x - lastTarget.x;
        state.pan[1] += controls.target.y - lastTarget.y;
        state.pan[2] += controls.target.z - lastTarget.z;
        state.panEvents++;
      }
      lastTarget.copy(controls.target);
    });
    // Native follow-camera updates supply an unshifted camera. Keep only the
    // user's view offset across those updates; no scene object is translated.
    const update = view.updateCameraSmooth;
    view.updateCameraSmooth = function (...args) {
      applying = true;
      try { translate(this, -1); update.apply(this, args); translate(this, 1); }
      finally { lastTarget.copy(controls.target); applying = false; }
    };
  }
  function apply() {
    const canvas = active(), view = canvas?.windowCamera, camera = view?.camera;
    attachPan(view);
    if (camera && Math.abs(camera.zoom - state.factor) > 1e-9) {
      camera.zoom = state.factor;
      camera.updateProjectionMatrix();
    }
    const visibleCanvas = [...document.querySelectorAll('canvas[data-engine]')]
      .find(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0);
    if (visibleCanvas && camera) {
      if (!badge) {
        badge = document.createElement('div');
        badge.dataset.maritimeZoom = 'true';
        badge.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;padding:5px 9px;border-radius:5px;background:rgba(255,255,255,.85);color:#193547;font:13px Arial,sans-serif';
        document.body.appendChild(badge);
      }
      const rect = visibleCanvas.getBoundingClientRect();
      badge.style.display = '';
      badge.style.left = Math.max(rect.left + 5, rect.right - 172) + 'px';
      badge.style.top = rect.top + 8 + 'px';
      const label = `中键平移 · ${state.factor.toFixed(2)}×`;
      if (badge.textContent !== label) badge.textContent = label;
    } else if (badge) badge.style.display = 'none';
    requestAnimationFrame(apply);
  }
  document.addEventListener('wheel', event => {
    if (!event.ctrlKey || !(event.target instanceof Element) || !event.target.closest('canvas[data-engine]') || !active()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const dy = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? innerHeight : 1);
    state.factor = Math.max(state.min, Math.min(state.max, state.factor * Math.exp(-Math.max(-240, Math.min(240, dy)) * .0015)));
    state.wheelEvents++;
  }, {capture: true, passive: false});
  document.addEventListener('pointerdown', event => {
    if (event.button === 1 && event.target instanceof Element && event.target.closest('canvas[data-engine]') && active()) {
      dragging = true;
    }
    const button = event.target instanceof Element && event.target.closest('g.control[type="ControlButton"]');
    const label = button?.textContent?.trim() || '';
    if (label === '重置相机' || label === '维港全景' || label === '全景 / 跟随特写' || /^M[1-4] /.test(label) || ['正常直飞','同向绕行案例','相向避让','起点拒绝案例','建筑避障','孤立观测点'].includes(label)) {
      const view = active()?.windowCamera;
      if (view?.controls) { applying = true; translate(view, -1); applying = false; }
      state.pan = [0, 0, 0]; state.factor = 1;
    }
  }, true);
  // Cancelling pointerdown can suppress the compatibility mouse events used
  // by the bundled OrbitControls. Prevent browser autoscroll on mousedown only.
  document.addEventListener('mousedown', event => {
    if (event.button === 1 && event.target instanceof Element && event.target.closest('canvas[data-engine]') && active()) { dragging = true; event.preventDefault(); }
  }, true);
  document.addEventListener('mouseup', event => { if (event.button === 1) dragging = false; }, true);
  window.addEventListener('blur', () => { dragging = false; });
  requestAnimationFrame(apply);
})();
