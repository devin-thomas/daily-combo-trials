const showArtworkFallback = (image) => {
  const fallback = document.getElementById(image.dataset.fallbackTarget);
  if (!fallback) return;

  image.hidden = true;
  fallback.hidden = false;
};

document.addEventListener(
  "error",
  (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.dataset.artImage) return;

    showArtworkFallback(image);
  },
  true,
);

document.querySelectorAll("img[data-art-image]").forEach((image) => {
  if (image.complete && image.naturalWidth === 0) showArtworkFallback(image);
});
