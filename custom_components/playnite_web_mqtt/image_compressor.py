import asyncio
from io import BytesIO
import logging

from PIL import Image

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_IMAGE_SIZE_BYTES = 14500
DEFAULT_MIN_QUALITY = 60
DEFAULT_INITIAL_QUALITY = 95
DEFAULT_QUALITY_STEP = 10
DEFAULT_MAX_CONCURRENT_COMPRESSIONS = 5


class ImageCompressor:
    """Utility class for compressing images asynchronously using WebP."""

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
        :param max_concurrent_compressions: max num of concurrent
        """
        self.max_size = max_size
        self.min_quality = min_quality
        self.initial_quality = initial_quality
        self.quality_step = DEFAULT_QUALITY_STEP
        self.compression_semaphore = asyncio.Semaphore(
            max_concurrent_compressions
        )
        self._buffer = BytesIO()

    async def compress_image(self, image_data: bytes) -> bytes:
        """Compress the image async by reducing quality or resizing."""
        image = Image.open(BytesIO(image_data))
        initial_size = len(image_data)
        if initial_size <= self.max_size:
            _LOGGER.info(
                "Image is already within the size limit %d bytes < %d bytes. "
                "No compression needed",
                initial_size,
                self.max_size,
            )
            return image_data

        _LOGGER.info(
            "Initial image size: %d bytes > %d bytes",
            initial_size,
            self.max_size,
        )

        compressed_image_data = await asyncio.get_event_loop().run_in_executor(
            None, self._progressive_quality_compression, image
        )

        if len(compressed_image_data) > self.max_size:
            _LOGGER.info(
                "Image size %d bytes too large after quality, resize it",
                len(compressed_image_data),
            )
            compressed_image_data = (
                await asyncio.get_event_loop().run_in_executor(
                    None, self._resize_and_compress, image
                )
            )

        _LOGGER.info(
            "Accepted image size: %d bytes", len(compressed_image_data)
        )
        return compressed_image_data

    def _progressive_quality_compression(self, image: Image.Image) -> bytes:
        """Reduce image quality until the size constraint is met."""
        quality = self.initial_quality
        while quality >= self.min_quality:
            compressed_image_data = self._apply_compression(image, quality)
            if len(compressed_image_data) <= self.max_size:
                _LOGGER.info(
                    "Compressed image size: %d bytes at quality %d",
                    len(compressed_image_data),
                    quality,
                )
                return compressed_image_data

            _LOGGER.info(
                "Size %d bytes too large at quality %d, trying lower quality",
                len(compressed_image_data),
                quality,
            )
            quality -= self.quality_step
        return compressed_image_data

    def _apply_compression(self, image: Image.Image, quality: int) -> bytes:
        """Apply compression by reducing image quality using WebP."""
        self._buffer.seek(0)
        self._buffer.truncate(0)
        # if image.mode == "RGBA":
        #     image = image.convert("RGB")
        image.save(
            self._buffer,
            lossless=False,
            alpha_quality=quality,
            exact=False,
            optimize=True,
            format="WEBP",
            quality=quality,
        )
        return self._buffer.getvalue()

    def _resize_and_compress(self, image: Image.Image) -> bytes:
        """Resize and compress the image to meet the size constraint."""
        width, height = image.size
        resize_factor = 0.75
        while True:
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
            compressed_image_data = self._apply_compression(
                resized_image, self.min_quality
            )

            if (
                len(compressed_image_data) <= self.max_size
                or resize_factor <= 0.25
            ):
                _LOGGER.info(
                    "Final resized image size: %d bytes",
                    len(compressed_image_data),
                )
                return compressed_image_data

            resize_factor -= 0.25
