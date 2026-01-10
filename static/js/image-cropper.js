let cropper = null;
let activeInput = null;

document.addEventListener("DOMContentLoaded", () => {

  document.querySelectorAll(".image-input").forEach(input => {
    input.addEventListener("change", e => {
      if (!e.target.files || !e.target.files.length) return;

      activeInput = e.target;

      const file = e.target.files[0];
      const reader = new FileReader();

      reader.onload = () => {
        openCropModal(reader.result);
      };

      reader.readAsDataURL(file);
    });
  });

  document.getElementById("cropConfirmBtn")
    .addEventListener("click", applyCrop);
});

function openCropModal(imageSrc) {
  const img = document.getElementById("cropperImage");
  const modalEl = document.getElementById("imageCropModal");

  img.src = imageSrc;

  const modal = new bootstrap.Modal(modalEl);
  modal.show();

  // ⚠️ IMPORTANT: wait until modal is fully visible
  modalEl.addEventListener(
    "shown.bs.modal",
    () => {
      if (cropper) {
        cropper.destroy();
        cropper = null;
      }

      cropper = new Cropper(img, {
        aspectRatio: 1,
        viewMode: 1,
        autoCropArea: 0.9,
        responsive: true,
        background: false,
        zoomable: true,
        scalable: true,
        movable: true,
      });
    },
    { once: true } // prevent duplicate init
  );
}


function applyCrop() {
  if (!cropper || !activeInput) return;

  cropper.getCroppedCanvas({
    width: 600,
    height: 600,
    imageSmoothingQuality: "high",
  }).toBlob(blob => {

    const file = new File(
      [blob],
      activeInput.name + ".jpg",
      { type: "image/jpeg" }
    );

    const dt = new DataTransfer();
    dt.items.add(file);
    activeInput.files = dt.files;

    cropper.destroy();
    cropper = null;

    bootstrap.Modal
      .getInstance(document.getElementById("imageCropModal"))
      .hide();

  }, "image/jpeg", 0.9);
}
