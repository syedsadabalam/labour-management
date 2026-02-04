/* ===============================
   IMAGE CROPPER – FINAL VERSION
   =============================== */

let cropper = null;
let activeInput = null;
let cropModal = null;

// Ensure modal exists
document.addEventListener("DOMContentLoaded", () => {
    const modalEl = document.getElementById("imageCropModal");
    if (!modalEl) return;

    cropModal = new bootstrap.Modal(modalEl);

    modalEl.addEventListener("shown.bs.modal", () => {
        const cropBtn = document.getElementById("cropConfirmBtn");
        if (cropBtn) {
            cropBtn.onclick = applyCrop; // overwrite safely
        }
    });

    modalEl.addEventListener("hidden.bs.modal", () => {
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
    });
});


// Attach to all image file inputs
document.addEventListener("change", function (e) {
    const input = e.target;

    if (
        input.tagName !== "INPUT" ||
        input.type !== "file" ||
        !input.classList.contains("image-input")
    ) {
        return;
    }

    if (!input.files || !input.files[0]) return;

    activeInput = input;
    const file = input.files[0];

    const reader = new FileReader();
    reader.onload = function () {
        const img = document.getElementById("cropperImage");
        img.src = reader.result;

        cropModal.show();

        if (cropper) cropper.destroy();

        cropper = new Cropper(img, {
            aspectRatio: 1,
            viewMode: 1,
            autoCropArea: 1,
            responsive: true,
            background: false,
        });
    };

    reader.readAsDataURL(file);
});

// Crop & Save button
const cropBtn = document.getElementById("cropConfirmBtn");
if (cropBtn) {
    cropBtn.addEventListener("click", applyCrop);
}

function applyCrop() {
    if (!cropper || !activeInput) return;

    const canvas = cropper.getCroppedCanvas({
        width: 1200,
        height: 1200,
        imageSmoothingEnabled: true,
        imageSmoothingQuality: "high",
    });

    canvas.toBlob(
        (blob) => {
            const fileName = activeInput.name + ".jpg";

            const croppedFile = new File(
                [blob],
                fileName,
                { type: "image/jpeg" }
            );

            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(croppedFile);

            // 🔥 THIS LINE MAKES EVERYTHING WORK
            activeInput.files = dataTransfer.files;

            // Cleanup
            cropper.destroy();
            cropper = null;
            cropModal.hide();

            activeInput = null;
        },
        "image/jpeg",
        0.9
    );
}
