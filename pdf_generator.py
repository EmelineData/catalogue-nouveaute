from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


PDF_FONTS = {
    "Helvetica": ("Helvetica", "Helvetica-Bold"),
    "Times": ("Times-Roman", "Times-Bold"),
    "Courier": ("Courier", "Courier-Bold"),
}


PAGE_LAYOUTS = {
    2: (1, 2),
    4: (2, 2),
    6: (2, 3),
}


def text_value(value: Any) -> str:
    """Return a display-safe value from a pandas cell."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def wrap_text(
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
    max_lines: int,
) -> list[str]:
    """Wrap text to a measured width and truncate the final line if needed."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    if len(lines) <= max_lines:
        return lines

    lines = lines[:max_lines]
    last_line = lines[-1]
    while last_line and stringWidth(
        f"{last_line}…", font_name, font_size
    ) > max_width:
        last_line = last_line[:-1].rstrip()
    lines[-1] = f"{last_line}…"
    return lines


def draw_wrapped_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    x: float,
    y: float,
    font_name: str,
    font_size: float,
    leading: float,
    color: colors.Color,
) -> float:
    """Draw left-aligned lines and return the y-coordinate below them."""
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def author_for_row(row: pd.Series) -> str:
    """Combine the optional first and last author names."""
    return " ".join(
        value
        for value in [
            text_value(row.get("prenom_auteur")),
            text_value(row.get("nom_auteur")),
        ]
        if value
    )


def image_for_row(
    row: pd.Series,
    cover_results: dict[str, dict[str, bytes | str | None]],
    fallback_cover: bytes,
) -> bytes:
    """Return the BnF image for a row, or the generic placeholder."""
    isbn = text_value(row.get("isbn_nettoye"))
    result = cover_results.get(isbn, {})
    image = result.get("image")
    return image if isinstance(image, bytes) else fallback_cover


def draw_cover(
    pdf: canvas.Canvas,
    image_bytes: bytes,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    """Draw an image in a bounding box while preserving its proportions."""
    try:
        image = ImageReader(BytesIO(image_bytes))
        image_width, image_height = image.getSize()
        scale = min(width / image_width, height / image_height)
        drawn_width = image_width * scale
        drawn_height = image_height * scale
        pdf.drawImage(
            image,
            x + (width - drawn_width) / 2,
            y + (height - drawn_height) / 2,
            width=drawn_width,
            height=drawn_height,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        pdf.setFillColor(colors.HexColor("#F2EFE9"))
        pdf.rect(x, y, width, height, stroke=0, fill=1)


def draw_book_card(
    pdf: canvas.Canvas,
    row: pd.Series,
    cover_results: dict[str, dict[str, bytes | str | None]],
    fallback_cover: bytes,
    selected_fields: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    books_per_page: int,
    regular_font: str,
    bold_font: str,
    body_font_size: float,
    show_card_borders: bool,
) -> None:
    """Draw one book card inside the supplied rectangle."""
    card_padding = 10
    compact = books_per_page == 6
    body_size = body_font_size - 1 if compact else body_font_size
    title_size = body_size + 1.7
    title_leading = title_size + 2
    body_leading = body_size + 2

    pdf.setFillColor(colors.HexColor("#F8FAF9"))
    pdf.setStrokeColor(colors.HexColor("#CAD8D2"))
    pdf.roundRect(
        x, y, width, height, 7,
        stroke=1 if show_card_borders else 0,
        fill=1,
    )

    text_area_height = max(78, height * (0.34 if compact else 0.32))
    cover_box_x = x + card_padding
    cover_box_y = y + text_area_height
    cover_box_width = width - 2 * card_padding
    cover_box_height = height - text_area_height - card_padding

    draw_cover(
        pdf,
        image_for_row(row, cover_results, fallback_cover),
        cover_box_x,
        cover_box_y,
        cover_box_width,
        cover_box_height,
    )

    text_x = x + card_padding
    text_width = width - 2 * card_padding
    cursor_y = y + text_area_height - 15

    title = text_value(row.get("titre")) or "Titre non renseigné"
    title_lines = wrap_text(
        title,
        bold_font,
        title_size,
        text_width,
        max_lines=2 if compact else 3,
    )
    cursor_y = draw_wrapped_lines(
        pdf,
        title_lines,
        text_x,
        cursor_y,
        bold_font,
        title_size,
        title_leading,
        colors.HexColor("#244B5A"),
    )
    cursor_y -= 2

    detail_lines: list[str] = []
    if "Auteur" in selected_fields:
        author = author_for_row(row)
        if author:
            detail_lines.append(author)

    year = text_value(row.get("annee"))
    genre = text_value(row.get("genre"))
    metadata: list[str] = []
    if "Année" in selected_fields and year:
        metadata.append(year)
    if "Genre" in selected_fields and genre:
        metadata.append(genre)
    if metadata:
        detail_lines.append(" - ".join(metadata))

    shelfmark = text_value(row.get("cote"))
    if "Cote" in selected_fields and shelfmark:
        detail_lines.append(f"Cote : {shelfmark}")

    isbn = text_value(row.get("isbn"))
    if "ISBN" in selected_fields and isbn:
        detail_lines.append(f"ISBN : {isbn}")

    max_detail_lines = 3 if compact else 4
    for detail in detail_lines[:max_detail_lines]:
        wrapped = wrap_text(
            detail,
            regular_font,
            body_size,
            text_width,
            max_lines=1,
        )
        cursor_y = draw_wrapped_lines(
            pdf,
            wrapped,
            text_x,
            cursor_y,
            regular_font,
            body_size,
            body_leading,
            colors.HexColor("#465650"),
        )


def build_catalogue_pdf(
    catalogue: pd.DataFrame,
    cover_results: dict[str, dict[str, bytes | str | None]],
    fallback_cover: bytes,
    document_title: str,
    books_per_page: int,
    selected_fields: list[str],
    header_color: str = "#244B5A",
    header_text_color: str = "#FFFFFF",
    font_family: str = "Helvetica",
    header_font_size: int = 16,
    body_font_size: float = 8.8,
    show_card_borders: bool = True,
) -> bytes:
    """Generate the complete catalogue and return its PDF bytes."""
    if books_per_page not in PAGE_LAYOUTS:
        raise ValueError("Le nombre de livres par page doit être 2, 4 ou 6.")
    if catalogue.empty:
        raise ValueError("Le catalogue ne contient aucun ouvrage.")
    if font_family not in PDF_FONTS:
        raise ValueError("La police PDF sélectionnée n'est pas reconnue.")

    regular_font, bold_font = PDF_FONTS[font_family]
    header_fill = colors.HexColor(header_color)
    header_text_fill = colors.HexColor(header_text_color)

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    page_width, page_height = A4

    columns, rows = PAGE_LAYOUTS[books_per_page]
    margin_x = 28
    header_height = 52
    footer_height = 24
    gap = 10
    content_top = page_height - header_height - 12
    content_bottom = footer_height + 10
    content_width = page_width - 2 * margin_x
    content_height = content_top - content_bottom
    card_width = (content_width - gap * (columns - 1)) / columns
    card_height = (content_height - gap * (rows - 1)) / rows

    total_pages = (len(catalogue) + books_per_page - 1) // books_per_page

    for page_number in range(total_pages):
        pdf.setFillColor(header_fill)
        pdf.rect(0, page_height - header_height, page_width, header_height, stroke=0, fill=1)
        pdf.setFillColor(header_text_fill)
        pdf.setFont(bold_font, header_font_size)
        header_lines = wrap_text(
            document_title or "Les nouveautés de la bibliothèque",
            bold_font,
            header_font_size,
            page_width - 80,
            max_lines=2,
        )
        first_header_y = page_height - 22 if len(header_lines) > 1 else page_height - 31
        for line_index, line in enumerate(header_lines):
            pdf.drawCentredString(
                page_width / 2,
                first_header_y - line_index * 18,
                line,
            )

        start = page_number * books_per_page
        end = min(start + books_per_page, len(catalogue))
        page_rows = catalogue.iloc[start:end]

        for position, (_, book) in enumerate(page_rows.iterrows()):
            grid_row = position // columns
            grid_column = position % columns
            card_x = margin_x + grid_column * (card_width + gap)
            card_y = content_top - (grid_row + 1) * card_height - grid_row * gap
            draw_book_card(
                pdf,
                book,
                cover_results,
                fallback_cover,
                selected_fields,
                card_x,
                card_y,
                card_width,
                card_height,
                books_per_page,
                regular_font,
                bold_font,
                body_font_size,
                show_card_borders,
            )

        pdf.setFont(regular_font, 7.5)
        pdf.setFillColor(colors.HexColor("#5C6B73"))
        pdf.drawString(
            margin_x,
            14,
            "Couvertures : Bibliothèque nationale de France - "
            f"récupération le {date.today().strftime('%d/%m/%Y')}",
        )
        pdf.drawRightString(
            page_width - margin_x,
            14,
            f"Page {page_number + 1} / {total_pages}",
        )
        pdf.showPage()

    pdf.save()
    return output.getvalue()
