from PIL import Image
import io

class ImageProcessor:
    """Utilities for optimizing images before sending to VLM."""

    @staticmethod
    def resize_image(image_bytes: bytes, max_dimension: int = 1200) -> bytes:
        """Resize image while maintaining aspect ratio."""
        img = Image.open(io.BytesIO(image_bytes))

        # Calculate new dimensions
        width, height = img.size
        if max(width, height) > max_dimension:
            if width > height:
                new_width = max_dimension
                new_height = int(height * (max_dimension / width))
            else:
                new_height = max_dimension
                new_width = int(width * (max_dimension / height))

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save back to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
