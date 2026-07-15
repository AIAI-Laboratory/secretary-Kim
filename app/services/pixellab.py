import base64
import httpx
from typing import Optional
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class PixelLabError(Exception):
    """Base exception for PixelLab Service errors."""

    pass


class PaymentRequiredError(PixelLabError):
    """Exception raised when API returns 402 Insufficient credits."""

    pass


class PixelLabService:
    def __init__(self):
        self.base_url = "https://api.pixellab.ai/v2"

    async def generate_pixel_art(
        self,
        prompt: str,
        model: str = "pixflux",
        width: int = 128,
        height: int = 128,
        transparent: bool = True,
        init_image: Optional[bytes] = None,
        init_image_strength: int = 300,
    ) -> bytes:
        """
        Generate pixel art using the PixelLab API.

        Args:
            prompt: Text description of the image.
            model: The model to use ('pixflux', 'pixen', or 'bitforge').
            width: Image width.
            height: Image height.
            transparent: True to generate with a transparent background.
            init_image: Optional initial image bytes to guide generation.
            init_image_strength: Influence of the init image (1-999, default 300).

        Returns:
            bytes: Raw image bytes of the generated PNG.
        """
        # Validate settings
        if not settings.PIXELLAB_API_KEY:
            raise PixelLabError(
                "PIXELLAB_API_KEY has not been configured in the .env file!"
            )

        # Determine endpoint
        if model == "pixflux":
            endpoint = f"{self.base_url}/create-image-pixflux"
        elif model == "pixen":
            endpoint = f"{self.base_url}/create-image-pixen"
            if init_image:
                raise PixelLabError(
                    "Model 'pixen' does not support init_image reference."
                )
        elif model == "bitforge":
            endpoint = f"{self.base_url}/create-image-bitforge"
        else:
            raise PixelLabError(f"Unsupported model: {model}")

        headers = {
            "Authorization": f"Bearer {settings.PIXELLAB_API_KEY}",
            "Content-Type": "application/json",
        }

        if init_image:
            from PIL import Image
            import io

            try:
                img = Image.open(io.BytesIO(init_image))
                width, height = img.size
                logger.info(
                    f"Auto-adjusting generation size to match init_image size: {width}x{height}"
                )
            except Exception as e:
                logger.warning(f"Failed to read init_image size: {e}")

        payload = {
            "description": prompt,
            "image_size": {"width": width, "height": height},
            "no_background": transparent,
        }

        if init_image:
            encoded_init = base64.b64encode(init_image).decode("utf-8")
            payload["init_image"] = {
                "type": "base64",
                "base64": encoded_init,
                "format": "png",
            }
            payload["init_image_strength"] = init_image_strength

        logger.info(
            f"Calling PixelLab {model} endpoint for prompt: {prompt} ({width}x{height})"
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(endpoint, headers=headers, json=payload)
            except Exception as e:
                logger.error(f"Failed to connect to PixelLab API: {e}")
                raise PixelLabError(f"Failed to connect to PixelLab API: {e}")

            if response.status_code == 402:
                logger.warning("PixelLab API returned 402: Insufficient credits.")
                raise PaymentRequiredError("Hết giờ làm rồi, đợi ngày mai nhé 😴")
            elif response.status_code != 200:
                logger.error(
                    f"PixelLab API error ({response.status_code}): {response.text}"
                )
                raise PixelLabError(
                    f"PixelLab API error ({response.status_code}): {response.text}"
                )

            try:
                result = response.json()
                base64_data = result.get("image", {}).get("base64", "")
                if not base64_data:
                    raise PixelLabError("No image base64 data found in API response.")

                # Split prefix if present (e.g. data:image/png;base64,xxxx)
                if "," in base64_data:
                    base64_data = base64_data.split(",", 1)[1]

                return base64.b64decode(base64_data)
            except Exception as e:
                logger.error(f"Failed to parse PixelLab response: {e}")
                raise PixelLabError(f"Failed to parse PixelLab response: {e}")
