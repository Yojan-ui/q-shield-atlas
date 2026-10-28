// Re-export of the existing viz data layer (viz/data.js), so the web app and the 2D viz share one model.
// The relative path resolves to /viz/data.js in the browser and to repo/viz/data.js under node.
export * from "../../../viz/data.js";
