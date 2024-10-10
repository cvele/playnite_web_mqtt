import logging
from io import BytesIO
from PIL import Image
import asyncio

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_IMAGE_SIZE_BYTES = 14500
DEFAULT_MIN_QUALITY = 60
DEFAULT_INITIAL_QUALITY = 95
DEFAULT_MAX_CONCURRENT_COMPRESSIONS = 5


class ImageCompressor:
    """Utility class for compressing images asynchronously."""

    def __init__(
        self,
        max_size=DEFAULT_MAX_IMAGE_SIZE_BYTES,
        min_quality=DEFAULT_MIN_QUALITY,
        initial_quality=DEFAULT_INITIAL_QUALITY,
        max_concurrent_compressions=DEFAULT_MAX_CONCURRENT_COMPRESSIONS,
    ) -> None:
        """Initialize the ImageCompressor.

        :param max_size: Maximum allowed image size in bytes.
        :param min_quality: Minimum quality for image compression.
        :param initial_quality: Initial quality for image compression.
        :param max_concurrent_compressions: Max # of concurrent compressions.
        """
        self.max_size = max_size
        self.min_quality = min_quality
        self.initial_quality = initial_quality
        self.compression_semaphore = asyncio.Semaphore(
            max_concurrent_compressions
        )
        self._buffer = BytesIO()  # Reusable BytesIO buffer

    async def compress_image(self, image_data: bytes) -> bytes:
        """Compress the image async by reducing quality or resizing."""
        if len(image_data) <= self.max_size:
            return image_data

        image = Image.open(BytesIO(image_data))
        initial_size = len(image_data)
        quality = self._calculate_initial_quality(initial_size)
        compressed_image_data = await asyncio.get_event_loop().run_in_executor(
            None, self._apply_compression, image, quality
        )

        # If compression based on quality is not enough, resize the image
        if len(compressed_image_data) > self.max_size:
            compressed_image_data = (
                await asyncio.get_event_loop().run_in_executor(
                    None, self._resize_image, image, quality
                )
            )

        return compressed_image_data

    def _calculate_initial_quality(self, initial_size: int) -> int:
        """Calculate the initial quality factor based on image size."""
        compression_factor = self.max_size / initial_size
        estimated_quality = int(self.initial_quality * compression_factor)
        return max(estimated_quality, self.min_quality)

    def _apply_compression(self, image: Image.Image, quality: int) -> bytes:
        """Apply compression by reducing image quality."""
        self._buffer.seek(0)
        self._buffer.truncate(0)

        if image.mode == "RGBA":
            image = image.convert("RGB")
        image.save(self._buffer, format="JPEG", quality=quality)
        compressed_image_data = self._buffer.getvalue()

        initial_size = len(image.tobytes())
        _LOGGER.info(
            "Compression process: Initial size: %d bytes, Quality: %d",
            initial_size,
            quality,
        )
        _LOGGER.info(
            "Compression result: Final size: %d bytes, Reduction: %.2f%%",
            len(compressed_image_data),
            (1 - len(compressed_image_data) / initial_size) * 100,
        )

        return compressed_image_data

    def _resize_image(self, image: Image.Image, quality: int) -> bytes:
        """Resize the image to meet the maximum size constraint."""
        width, height = image.size
        resize_factor = (self.max_size / len(image.tobytes())) ** 0.5
        new_width = int(width * resize_factor)
        new_height = int(height * resize_factor)

        _LOGGER.info(
            "Resizing image from %dx%d to %dx%d",
            width,
            height,
            new_width,
            new_height,
        )

        resized_image = image.resize(
            (new_width, new_height), Image.Resampling.BILINEAR
        )
        if resized_image.mode == "RGBA":
            resized_image = resized_image.convert("RGB")

        self._buffer.seek(0)
        self._buffer.truncate(0)
        resized_image.save(self._buffer, format="JPEG", quality=quality)
        resized_image_data = self._buffer.getvalue()

        _LOGGER.info(
            "Final resized image size: %d bytes", len(resized_image_data)
        )

        return resized_image_data
