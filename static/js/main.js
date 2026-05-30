document.addEventListener("DOMContentLoaded", () => {
    const attendanceForm = document.querySelector("[data-attendance-form]");
    if (attendanceForm) {
        const latitudeInput = attendanceForm.querySelector('input[name="latitude"]');
        const longitudeInput = attendanceForm.querySelector('input[name="longitude"]');
        const locationInput = attendanceForm.querySelector('input[name="location_text"]');
        const statusLabel = document.querySelector("[data-location-status]");
        const photoInput = attendanceForm.querySelector("[data-photo-input]");
        const photoPreview = attendanceForm.querySelector("[data-photo-preview]");

        const setStatus = (message, isError = false) => {
            if (!statusLabel) return;
            statusLabel.textContent = message;
            statusLabel.classList.toggle("text-danger", isError);
            statusLabel.classList.toggle("text-success", !isError);
        };

        const reverseGeocodeFallback = (lat, lng) => {
            return `Lat ${lat}, Lng ${lng}`;
        };

        const getLocation = () => {
            if (!navigator.geolocation) {
                setStatus("Geolocation is not supported in this browser.", true);
                return;
            }
            setStatus("Fetching current location...");
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude.toFixed(6);
                    const lng = position.coords.longitude.toFixed(6);
                    latitudeInput.value = lat;
                    longitudeInput.value = lng;
                    locationInput.value = reverseGeocodeFallback(lat, lng);
                    setStatus("Location captured successfully.");
                },
                () => {
                    setStatus("Unable to fetch location. Please allow browser location access.", true);
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        };

        const locationButton = document.querySelector("[data-get-location]");
        if (locationButton) {
            locationButton.addEventListener("click", getLocation);
        }

        if (photoInput && photoPreview) {
            photoInput.addEventListener("change", () => {
                const [file] = photoInput.files || [];
                if (!file) {
                    photoPreview.src = "";
                    photoPreview.classList.add("d-none");
                    return;
                }
                photoPreview.src = URL.createObjectURL(file);
                photoPreview.classList.remove("d-none");
            });
        }
        getLocation();
    }

    document.querySelectorAll("[data-auto-submit]").forEach((form) => {
        const inputs = form.querySelectorAll("select");
        inputs.forEach((input) => input.addEventListener("change", () => form.submit()));
    });
});
