import uuid
import warnings
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000

def normalize_image(upload):
    if upload.size > MAX_BYTES:
        raise ValidationError('图片不能超过 10 MB。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValidationError('仅支持 JPEG、PNG、WebP 图片。')
                if source.width * source.height > MAX_PIXELS:
                    raise ValidationError('图片像素过大，请压缩至 4000 万像素以下。')
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((2560, 2560))
                # Copy pixels to a fresh image so EXIF, GPS and other metadata cannot survive.
                rgba = oriented.convert('RGBA')
                clean = Image.new('RGBA', rgba.size)
                clean.paste(rgba)
                output = BytesIO()
                clean.save(output, format='WEBP', quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('图片损坏或格式无效，请重新选择图片。') from exc
    return ContentFile(output.getvalue(), name=f'{uuid.uuid4().hex}.webp')
