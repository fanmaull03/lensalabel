import test from "node:test";
import assert from "node:assert/strict";
import { cameraCrop } from "./cameraCrop.js";

test("crops the visible guide from a landscape video shown with object-cover", () => {
  assert.deepEqual(
    cameraCrop(
      { width: 1920, height: 1080 },
      { left: 0, top: 0, width: 390, height: 844 },
      { left: 24, top: 250, width: 342, height: 344 },
    ),
    { x: 741, y: 320, width: 438, height: 440 },
  );
});

test("crops the visible guide from a portrait video", () => {
  assert.deepEqual(
    cameraCrop(
      { width: 1080, height: 1920 },
      { left: 0, top: 0, width: 360, height: 640 },
      { left: 30, top: 100, width: 300, height: 400 },
    ),
    { x: 90, y: 300, width: 900, height: 1200 },
  );
});
