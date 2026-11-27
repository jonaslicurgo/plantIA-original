"use strict";

async function prepareDiagnosisPhoto(file, messages) {
    const maxSide = 1440;
    const targetBytes = 1900 * 1024;
    const accepted = ["image/jpeg", "image/png", "image/webp"];
    if (file.size > 32 * 1024 * 1024) throw new Error(messages.large);
    if (!accepted.includes(file.type)) throw new Error(messages.invalid);

    let image;
    try {
        image = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
        throw new Error(messages.invalid);
    }

    const canvas = document.createElement("canvas");
    try {
        const longest = Math.max(image.width, image.height);
        const scale = Math.min(1, maxSide / longest);
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        const context = canvas.getContext("2d", { alpha: false });
        context.fillStyle = "#fff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);

        for (const quality of [0.88, 0.80, 0.72]) {
            const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
            if (blob?.type === "image/jpeg" && blob.size <= targetBytes) return blob;
        }
        throw new Error(messages.large);
    } finally {
        image.close();
        canvas.width = canvas.height = 0;
    }
}

const diagnosisForm = document.querySelector("#health-diagnosis");
if (diagnosisForm && typeof createImageBitmap === "function" && HTMLCanvasElement.prototype.toBlob) {
    const gallery = diagnosisForm.elements.photo;
    const cameraLabel = document.querySelector("#health-camera");
    const camera = cameraLabel.querySelector("input");
    const fileName = document.querySelector("#health-photo-name");
    const error = document.querySelector("#health-diagnosis-error");
    const progress = document.querySelector("#health-diagnosis-progress");
    const submit = diagnosisForm.querySelector('button[type="submit"]');
    const messages = diagnosisForm.dataset;

    gallery.required = false;
    cameraLabel.hidden = false;
    for (const [input, other] of [[gallery, camera], [camera, gallery]]) {
        input.addEventListener("change", () => {
            if (input.files.length) other.value = "";
            fileName.textContent = (gallery.files[0] || camera.files[0])?.name || "";
            error.textContent = "";
        });
    }

    diagnosisForm.addEventListener("submit", async event => {
        event.preventDefault();
        if (submit.disabled) return;
        error.textContent = "";
        const file = gallery.files[0] || camera.files[0];
        if (!file || file.size === 0) {
            error.textContent = messages.missing;
            gallery.focus();
            return;
        }
        const body = new FormData(diagnosisForm);
        submit.disabled = gallery.disabled = camera.disabled = true;
        progress.textContent = messages.progress;
        try {
            let photo;
            try {
                photo = await prepareDiagnosisPhoto(file, messages);
            } catch (failure) {
                error.textContent = [messages.large, messages.invalid].includes(failure.message)
                    ? failure.message : messages.invalid;
                return;
            }
            body.set("photo", photo, "plant.jpg");
            const response = await fetch(messages.endpoint, {
                method: "POST", body, headers: { Accept: "application/json" }, redirect: "error"
            });
            if (response.status === 413) {
                error.textContent = messages.large;
                return;
            }
            if (!response.headers.get("content-type")?.includes("application/json")) {
                throw new Error();
            }
            const result = await response.json();
            if (!response.ok) {
                error.textContent = typeof result.detail === "string" ? result.detail : messages.failed;
                return;
            }
            if (!Number.isSafeInteger(result.id) || result.id < 1) throw new Error();
            const historyPath = diagnosisForm.action.replace(/\/avaliar$/, "");
            window.history.replaceState(null, "", historyPath + "#event-" + result.id);
            window.location.reload();
        } catch {
            error.textContent = messages.failed;
        } finally {
            submit.disabled = gallery.disabled = camera.disabled = false;
            progress.textContent = "";
        }
    });
}

if (/^#event-\d+$/.test(window.location.hash)) {
    document.getElementById(window.location.hash.slice(1))?.focus();
}
