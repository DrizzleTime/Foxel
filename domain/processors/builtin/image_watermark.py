from typing import Dict, Any
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from fastapi.responses import Response

from ..base import BaseProcessor


class ImageWatermarkProcessor:
    name = "图片水印"
    supported_exts = ["jpg", "jpeg", "png", "bmp"]
    config_schema = [
        {"key": "text", "label": "水印文字", "type": "string", "required": True},
        {
            "key": "position",
            "label": "位置",
            "type": "select",
            "required": False,
            "default": "bottom-right",
            "options": [
                {"value": "top-left", "label": "左上"},
                {"value": "center", "label": "居中"},
                {"value": "bottom-right", "label": "右下"},
            ],
        },
        {"key": "font_size", "label": "字体大小", "type": "number", "required": False, "default": 24},
    ]
    produces_file = True

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Response:
        text = config.get("text", "")
        position = config.get("position", "bottom-right")
        font_size = int(config.get("font_size", 24))

        img = Image.open(BytesIO(input_bytes)).convert("RGBA")
        watermark = Image.new("RGBA", img.size)
        draw = ImageDraw.Draw(watermark)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        w, h = img.size
        try:
            text_w, text_h = font.getsize(text)
        except AttributeError:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

        if position == "bottom-right":
            xy = (w - text_w - 10, h - text_h - 10)
        elif position == "top-left":
            xy = (10, 10)
        else:
            xy = (w // 2 - text_w // 2, h // 2 - text_h // 2)

        draw.text(xy, text, font=font, fill=(255, 255, 255, 128))
        out = Image.alpha_composite(img, watermark)
        buf = BytesIO()
        out.convert("RGB").save(buf, format="JPEG")

        return Response(content=buf.getvalue(), media_type="image/jpeg")


PROCESSOR_TYPE = "image_watermark"
PROCESSOR_NAME = ImageWatermarkProcessor.name
SUPPORTED_EXTS = ImageWatermarkProcessor.supported_exts
CONFIG_SCHEMA = ImageWatermarkProcessor.config_schema
PROCESSOR_FACTORY = lambda: ImageWatermarkProcessor()
