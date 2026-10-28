// THE LATTICE: one persistent full-screen layer. Stage 3 reserves it (no WebGL yet); Stage 4 mounts the
// single renderer here. Routes only tell it where the camera should be and which layers are visible.
export function createWorld(host) {
  const state = { camera: null, direction: "replace", layers: [] };
  return {
    host,
    state,
    go(camera, { direction = "forward", layers = [] } = {}) { Object.assign(state, { camera, direction, layers }); host.dataset.camera = camera; },
    setData() {},
  };
}
