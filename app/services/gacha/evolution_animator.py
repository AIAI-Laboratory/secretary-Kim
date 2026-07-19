import io
import math
import random
from typing import List
import httpx
from PIL import Image, ImageDraw
from app.core.logger import get_logger

logger = get_logger(__name__)


async def download_image_bytes(url: str) -> bytes:
    """Download image bytes from a URL with timeout protection."""
    logger.info(f"Downloading image for evolution animation from: {url}")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        return resp.content


def create_silhouette(img: Image.Image, color=(255, 255, 255, 255)) -> Image.Image:
    """Create a solid color silhouette from an RGBA image preserving transparency."""
    silhouette = Image.new("RGBA", img.size, color)
    silhouette.putalpha(img.getchannel("A"))
    return silhouette


def get_octagon_points(cx: int, cy: int, r: int) -> List[tuple]:
    """Calculate the 8 vertices of a regular octagon given a center and radius."""
    r_diag = int(r * 0.7071)
    return [
        (cx + r, cy),
        (cx + r_diag, cy - r_diag),
        (cx, cy - r),
        (cx - r_diag, cy - r_diag),
        (cx - r, cy),
        (cx - r_diag, cy + r_diag),
        (cx, cy + r),
        (cx + r_diag, cy + r_diag),
    ]


def draw_evolution_background(
    frame_idx: int, width: int = 128, height: int = 128, pet_id: int = 0
) -> Image.Image:
    """
    Render a frame of the evolution background.
    Draws concentric octagons that pulse/wave outwards, and white sparkles floating inwards.
    """
    bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    cx, cy = width // 2, height // 2

    # Glowing blue concentric octagon color palette matching Image 1
    # Drawn from largest to smallest to overlay correctly
    colors = [
        (138, 202, 230, 255),  # Light cyan-blue
        (188, 226, 242, 255),  # Soft cyan
        (82, 178, 223, 255),  # Bright sky blue
        (52, 142, 190, 255),  # Medium blue
        (227, 242, 253, 255),  # White-blue glow
        (255, 255, 255, 255),  # Pure white core
    ]
    num_rings = len(colors)

    for j in range(num_rings - 1, -1, -1):
        # Pulsing radius wave
        phase = (frame_idx * 15 - j * 30) % 360
        pulse = math.sin(math.radians(phase)) * 6
        r = int(15 + j * 12 + pulse)
        if r <= 0:
            continue

        color = colors[(j + frame_idx // 3) % len(colors)]
        points = get_octagon_points(cx, cy, r)
        draw.polygon(points, fill=color)

    # Sparkling floating particles converging to the center (Image 2 style)
    random.seed(pet_id + 999)  # Add salt to differentiate seed
    num_particles = 14
    for p in range(num_particles):
        theta = random.uniform(0, 2 * math.pi)
        r_start = random.uniform(60, 100)
        speed = random.uniform(2.5, 4.5)

        # Distance decreases over time, wrapping around
        distance = r_start - ((frame_idx * speed) % r_start)
        if distance < 6:
            continue  # Particles disappear close to the center

        px = int(cx + distance * math.cos(theta))
        py = int(cy + distance * math.sin(theta))
        p_radius = random.randint(1, 2)

        # Draw particle
        draw.ellipse(
            [px - p_radius, py - p_radius, px + p_radius, py + p_radius],
            fill=(255, 255, 255, 230),
        )

    return bg


def generate_charging_gif(current_png_bytes: bytes, pet_id: int) -> bytes:
    """
    Generate an animated GIF of the current pet charging/concentrating power.
    Pet flashes between normal and white silhouette over a pulsing octagon background.
    """
    current_img = Image.open(io.BytesIO(current_png_bytes)).convert("RGBA")
    current_img = current_img.resize((128, 128), Image.Resampling.NEAREST)
    current_silhouette = create_silhouette(current_img)

    frames = []
    # 15 frames charging (1.5 seconds)
    for i in range(15):
        frame = draw_evolution_background(i, 128, 128, pet_id)

        # Flashing pet (alternate normal and silhouette every frame)
        if i % 2 == 0:
            frame.alpha_composite(current_img)
        else:
            frame.alpha_composite(current_silhouette)

        frames.append(frame)

    # Save as transparent GIF
    out = io.BytesIO()
    processed_frames = []
    for f in frames:
        # Enforce clean binary alpha transparency for GIF
        r, g, b, a = f.split()
        a = a.point(lambda p: 255 if p > 128 else 0)
        clean_frame = Image.merge("RGBA", (r, g, b, a))
        processed_frames.append(clean_frame)

    processed_frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=processed_frames[1:],
        duration=100,
        loop=0,
        transparency=0,
        disposal=2,
    )
    return out.getvalue()


def generate_complete_evolution_gif(
    current_png_bytes: bytes, new_png_bytes: bytes, pet_id: int
) -> bytes:
    """
    Generate a full evolution sequence GIF:
    - Charging Phase (15 frames): Current pet flashing with glowing background and sparkles.
    - Morphing Phase (10 frames): Rapidly flashing old/new silhouettes with expanding explosion ring.
    - Reveal Phase (15 frames): New pet flashing, background fading out, settling into normal static new pet.
    """
    current_img = Image.open(io.BytesIO(current_png_bytes)).convert("RGBA")
    current_img = current_img.resize((128, 128), Image.Resampling.NEAREST)
    current_silhouette = create_silhouette(current_img)

    new_img = Image.open(io.BytesIO(new_png_bytes)).convert("RGBA")
    new_img = new_img.resize((128, 128), Image.Resampling.NEAREST)
    new_silhouette = create_silhouette(new_img)

    frames = []

    # 1. Charging Phase (15 frames)
    for i in range(15):
        frame = draw_evolution_background(i, 128, 128, pet_id)
        if i % 2 == 0:
            frame.alpha_composite(current_img)
        else:
            frame.alpha_composite(current_silhouette)
        frames.append(frame)

    # 2. Morphing Phase (10 frames)
    for i in range(10):
        frame_idx = 15 + i
        # Pulse background twice as fast
        frame = draw_evolution_background(frame_idx * 2, 128, 128, pet_id)

        # Draw an expanding white shockwave/explosion circle in center
        draw = ImageDraw.Draw(frame)
        exp_radius = int(8 + i * 9)
        draw.ellipse(
            [64 - exp_radius, 64 - exp_radius, 64 + exp_radius, 64 + exp_radius],
            fill=(255, 255, 255, 255),
        )

        # Morphing silhouettes
        if i % 2 == 0:
            frame.alpha_composite(current_silhouette)
        else:
            frame.alpha_composite(new_silhouette)
        frames.append(frame)

    # 3. Reveal Phase (15 frames)
    for i in range(15):
        frame = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Draw shrinking/fading octagon in the first 8 frames of reveal
        if i < 8:
            r = int(45 - i * 6)
            if r > 0:
                points = get_octagon_points(64, 64, r)
                draw.polygon(points, fill=(227, 242, 253, 255))

        # Flashing new pet settling down
        if i < 10:
            if i % 2 == 0:
                frame.alpha_composite(new_img)
            else:
                frame.alpha_composite(new_silhouette)
        else:
            # Final frames: stable new pet image
            frame.alpha_composite(new_img)

        frames.append(frame)

    # Save as transparent GIF
    out = io.BytesIO()
    processed_frames = []
    for f in frames:
        r, g, b, a = f.split()
        a = a.point(lambda p: 255 if p > 128 else 0)
        clean_frame = Image.merge("RGBA", (r, g, b, a))
        processed_frames.append(clean_frame)

    processed_frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=processed_frames[1:],
        duration=100,
        loop=0,
        transparency=0,
        disposal=2,
    )
    return out.getvalue()
