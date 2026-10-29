import assert from "node:assert/strict";
import { cameraCrop } from "../src/components/cameraCrop.js";

const box = (left, top, width, height) => ({ getBoundingClientRect: () => ({ left, top, width, height }) });
const video = Object.assign(box(0, 0, 1000, 1000), { videoWidth: 1920, videoHeight: 1080 });
assert.deepEqual(Object.values(cameraCrop(video, box(250, 250, 500, 500))).map(Math.round), [690, 270, 540, 540]);
const portrait = Object.assign(box(0, 0, 360, 640), { videoWidth: 1080, videoHeight: 1920 });
assert.deepEqual(Object.values(cameraCrop(portrait, box(24, 200, 312, 234))).map(Math.round), [72, 600, 936, 702]);
