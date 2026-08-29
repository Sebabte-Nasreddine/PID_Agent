from dataclasses import dataclass
from pathlib import Path
import hashlib
from pdf2image import convert_from_path
from PIL import Image
from app.models.chunk import Chunk,ChunkMetadata


@dataclass(frozen=True)
class GridConfig:
    n_rows: int = 2
    n_cols: int = 1
    overlap_px: int = 128
    dpi: int = 200
    min_acceptable_patch_px: int = 800
    max_acceptable_patch_px: int = 3200

def make_document_id(pdf_path:str)->str:
    resolved=Path(pdf_path).expanduser().resolve()
    with open(resolved,"rb") as f :
        content_hash=hashlib.sha256(f.read()).hexdigest()[:16]  #fait un hash et recuperer 16 premier caractere hexadicemal
    return f"{resolved.stem}_{content_hash}"   #.stem return pid01



def render_pdf_to_image(pdf_path: str, dpi: int = 200) -> Image.Image:
    resolved = str(Path(pdf_path).expanduser().resolve())
    pages = convert_from_path(resolved, dpi=dpi)
    if len(pages) != 1:
        raise ValueError(f"Expected a single-page PDF, got {len(pages)} pages: {resolved}")
    return pages[0]



#from ai

def _chunk_image(image: Image.Image, config: GridConfig) -> tuple[list[tuple[ChunkMetadata, Image.Image]], list[str]]:
    page_w_px, page_h_px = image.size
    core_w_px = page_w_px / config.n_cols
    core_h_px = page_h_px / config.n_rows

    errors = []
    if not (config.min_acceptable_patch_px <= core_w_px <= config.max_acceptable_patch_px):
        errors.append(f"Chunk width {core_w_px:.0f}px outside acceptable range")
    if not (config.min_acceptable_patch_px <= core_h_px <= config.max_acceptable_patch_px):
        errors.append(f"Chunk height {core_h_px:.0f}px outside acceptable range")

    raw_chunks: list[tuple[ChunkMetadata, Image.Image]] = []
    for row in range(config.n_rows):
        for col in range(config.n_cols):
            core_x0, core_y0 = col * core_w_px, row * core_h_px
            core_x1 = min(page_w_px, (col + 1) * core_w_px)
            core_y1 = min(page_h_px, (row + 1) * core_h_px)

            x0 = max(0.0, core_x0 - config.overlap_px)
            y0 = max(0.0, core_y0 - config.overlap_px)
            x1 = min(page_w_px, core_x1 + config.overlap_px)
            y1 = min(page_h_px, core_y1 + config.overlap_px)

            crop = image.crop((int(x0), int(y0), int(x1), int(y1)))

            metadata = ChunkMetadata(
                chunk_id=f"r{row}_c{col}",
                row=row, col=col,
                n_rows=config.n_rows, n_cols=config.n_cols,
                bbox_px=(x0, y0, x1, y1),
                core_bbox_px=(core_x0, core_y0, core_x1, core_y1),
            )
            raw_chunks.append((metadata, crop))

    return raw_chunks, errors



def chunk_pdf(pdf_path: str, document_id: str, config: GridConfig = GridConfig()) -> tuple[list[Chunk], list[str]]:
    image = render_pdf_to_image(pdf_path, dpi=config.dpi)
    raw_chunks, errors = _chunk_image(image, config)

    out_dir = Path("chunks") / document_id
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_chunks: list[Chunk] = []
    for metadata, crop in raw_chunks:
        image_path = str(out_dir / f"{metadata.chunk_id}.png")
        crop.save(image_path)
        saved_chunks.append(Chunk(metadata=metadata, image_path=image_path))

    return saved_chunks, errors