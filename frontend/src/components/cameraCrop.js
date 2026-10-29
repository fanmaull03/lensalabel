export function cameraCrop(video, frame) {
  const viewport = video.getBoundingClientRect();
  const target = frame.getBoundingClientRect();
  const scale = Math.max(viewport.width / video.videoWidth, viewport.height / video.videoHeight);
  return {
    x: (target.left - viewport.left + (video.videoWidth * scale - viewport.width) / 2) / scale,
    y: (target.top - viewport.top + (video.videoHeight * scale - viewport.height) / 2) / scale,
    width: target.width / scale,
    height: target.height / scale,
  };
}
