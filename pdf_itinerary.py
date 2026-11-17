from __future__ import annotations

import base64
import io
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import images

logger = logging.getLogger(__name__)
PAPER = colors.HexColor("#EEF2F6")
COBALT = colors.HexColor("#1D4ED8")
LATERITE = colors.HexColor("#B8461B")
INK = colors.HexColor("#0D1B2E")
MUTED = colors.HexColor("#46586E")
LINE = colors.HexColor("#C7D2E0")
WHITE = colors.white
CATEGORIES = ("stay", "food", "transport", "activities", "misc")


def build_itinerary_pdf(trip: dict[str, Any]) -> bytes:
    """Render a saved trip into a self-contained, paginated itinerary PDF."""
    itinerary_result = trip.get("itinerary") or {}
    itinerary = itinerary_result.get("itinerary") if isinstance(itinerary_result, dict) else {}
    itinerary = itinerary if isinstance(itinerary, dict) else {}
    raw_days = itinerary.get("days_plan")
    day_plans = raw_days if isinstance(raw_days, list) else []
    try:
        day_count = max(0, min(60, int(trip.get("days") or len(day_plans))))
    except (TypeError, ValueError):
        day_count = len(day_plans)

    interests = _string_list(trip.get("interests") or itinerary.get("interests"))
    cover_name = str(trip.get("destination") or itinerary.get("destination") or "Trip")
    image_requests: dict[str, tuple[str, str]] = {
        _asset_key(cover_name): (cover_name, cover_name),
    }
    for day in day_plans:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops", []):
            if isinstance(stop, dict) and stop.get("name"):
                name = str(stop["name"])
                image_requests[_asset_key(name)] = (name, cover_name)
    if not any(day.get("stops") for day in day_plans if isinstance(day, dict)):
        for interest in interests:
            image_requests[_asset_key(interest)] = (interest, cover_name)
    assets = _fetch_images(image_requests)
    credits = _image_credits(assets)

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=f"{cover_name} itinerary",
        author="Travel Planner",
    )
    styles = _styles()
    story = []
    width = document.width
    story.extend(_cover_page(trip, itinerary, cover_name, assets, styles, width))
    story.append(PageBreak())
    story.extend(_glance_page(trip, itinerary, day_plans, interests, styles, width))
    story.append(PageBreak())
    story.extend(_budget_page(trip, itinerary, styles, width))

    if day_count:
        story.append(PageBreak())
    for day_number in range(1, day_count + 1):
        day = next(
            (item for item in day_plans if isinstance(item, dict) and item.get("day") == day_number),
            day_plans[day_number - 1] if day_number <= len(day_plans) and isinstance(day_plans[day_number - 1], dict) else {},
        )
        story.extend(
            _day_page(
                trip,
                day,
                day_number,
                interests,
                assets,
                styles,
                width,
            )
        )
        if day_number < day_count:
            story.append(PageBreak())

    story.append(PageBreak())
    story.extend(_closing_page(trip, itinerary, itinerary_result, credits, styles))
    document.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return buffer.getvalue()


def _register_fonts() -> tuple[str, str]:
    fonts = (
        ("TravelSans", "TravelSans-Bold", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        ("TravelSans", "TravelSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for regular_name, bold_name, regular_path, bold_path in fonts:
        try:
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            return regular_name, bold_name
        except (OSError, ValueError):
            continue
    return "Helvetica", "Helvetica-Bold"


_FONT_REGULAR, _FONT_BOLD = _register_fonts()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle("TravelEyebrow", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=8, leading=11, textColor=LATERITE, spaceAfter=5),
        "title": ParagraphStyle("TravelTitle", parent=base["Title"], fontName=_FONT_BOLD, fontSize=31, leading=36, alignment=TA_LEFT, textColor=INK, spaceAfter=8),
        "heading": ParagraphStyle("TravelHeading", parent=base["Heading1"], fontName=_FONT_BOLD, fontSize=21, leading=26, textColor=INK, spaceAfter=12),
        "subheading": ParagraphStyle("TravelSubheading", parent=base["Heading2"], fontName=_FONT_BOLD, fontSize=12, leading=16, textColor=COBALT, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("TravelBody", parent=base["BodyText"], fontName=_FONT_REGULAR, fontSize=9.5, leading=14, textColor=INK, spaceAfter=5),
        "small": ParagraphStyle("TravelSmall", parent=base["BodyText"], fontName=_FONT_REGULAR, fontSize=8, leading=11, textColor=MUTED, spaceAfter=3),
        "hero": ParagraphStyle("TravelHero", parent=base["Title"], fontName=_FONT_BOLD, fontSize=34, leading=39, alignment=TA_LEFT, textColor=WHITE),
        "hero_meta": ParagraphStyle("TravelHeroMeta", parent=base["BodyText"], fontName=_FONT_REGULAR, fontSize=10, leading=15, textColor=WHITE),
        "center": ParagraphStyle("TravelCenter", parent=base["BodyText"], fontName=_FONT_REGULAR, fontSize=9, leading=13, alignment=TA_CENTER, textColor=MUTED),
        "cost": ParagraphStyle("TravelCost", parent=base["BodyText"], fontName=_FONT_BOLD, fontSize=9.5, leading=13, textColor=INK),
    }


def _cover_page(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    destination: str,
    assets: dict[str, dict[str, str]],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    asset = assets[_asset_key(destination)]
    hero = _image_flowable(asset, width, 78 * mm)
    hero_panel = Table(
        [
            [hero],
            [Paragraph(escape(destination), styles["hero"])],
            [Paragraph(_cover_meta(trip, itinerary), styles["hero_meta"])],
        ],
        colWidths=[width],
    )
    hero_panel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COBALT),
                ("BOX", (0, 0), (-1, -1), 0.1, COBALT),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 1), (-1, 1), 18),
                ("RIGHTPADDING", (0, 1), (-1, 1), 18),
                ("TOPPADDING", (0, 1), (-1, 1), 14),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 18),
            ]
        )
    )
    return [
        Paragraph("YOUR TRIP, THOUGHTFULLY PLANNED", styles["eyebrow"]),
        hero_panel,
        Spacer(1, 12 * mm),
        Paragraph("A considered itinerary, built around the details you shared.", styles["body"]),
        Spacer(1, 5 * mm),
        Paragraph(
            f"Planning allocations and place details are based only on the saved trip. "
            f"Image credits and sources are listed at the end.",
            styles["small"],
        ),
    ]


def _cover_meta(trip: dict[str, Any], itinerary: dict[str, Any]) -> str:
    dates = _date_range(trip, itinerary)
    travelers = _traveler_text(trip, itinerary)
    currency = _text(trip.get("currency") or itinerary.get("currency"))
    budget = _money(trip.get("budget", itinerary.get("budget")), currency)
    return "<br/>".join(
        escape(value)
        for value in (dates, travelers, f"Total budget: {budget}")
        if value
    )


def _glance_page(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    day_plans: list[dict[str, Any]],
    interests: list[str],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    planning = itinerary.get("planning_preferences") or {}
    if not isinstance(planning, dict):
        planning = {}
    facts = _trip_facts(trip, itinerary, interests, planning)
    data = [
        [Paragraph(f"<b>{escape(label)}</b>", styles["small"]), Paragraph(escape(value or "Not specified"), styles["body"])]
        for label, value in facts
    ]
    table = Table(data, colWidths=[width * 0.28, width * 0.72], hAlign="LEFT")
    table.setStyle(_card_table_style())
    story: list[Any] = [Paragraph("Trip at a glance", styles["heading"]), table]
    weather_rows = []
    for index, day in enumerate(day_plans, start=1):
        if not isinstance(day, dict):
            continue
        weather = _day_weather(day)
        if weather:
            weather_rows.append(
                [
                    Paragraph(f"<b>Day {escape(str(day.get('day', index)))}</b>", styles["small"]),
                    Paragraph(escape(" · ".join(value for value in (day.get("date"), weather) if value)), styles["body"]),
                ]
            )
    if weather_rows:
        story.extend(
            [
                Spacer(1, 7 * mm),
                Paragraph("Weather in the saved itinerary", styles["subheading"]),
            ]
        )
        weather_table = Table(weather_rows, colWidths=[width * 0.22, width * 0.78], hAlign="LEFT")
        weather_table.setStyle(_card_table_style())
        story.append(weather_table)
    return story


def _trip_facts(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    interests: list[str],
    planning: dict[str, Any],
) -> list[tuple[str, str]]:
    budget_mode = _text(trip.get("budget_mode") or planning.get("budget_mode"))
    budget_mode = {
        "total": "Total for the trip",
        "per_person": "Per person",
    }.get(budget_mode, budget_mode)
    flexible_dates = trip.get("flexible_dates", planning.get("flexible_dates"))
    date_flexibility = (
        "Flexible by up to 2 days" if flexible_dates else "Fixed dates"
    ) if isinstance(flexible_dates, bool) else ""
    areas = _string_list(trip.get("areas") or planning.get("areas"))
    food_styles = _string_list(trip.get("food_styles") or planning.get("food_styles"))
    return [
        ("Dates", _date_range(trip, itinerary)),
        ("Length", _format_days(trip.get("days", itinerary.get("days")))),
        ("Group", _traveler_text(trip, itinerary)),
        ("Pace", _text(trip.get("pace") or itinerary.get("pace"))),
        ("Interests", ", ".join(interests) or "Not specified"),
        ("Areas", ", ".join(areas) or "No specific area selected"),
        ("Budget basis", budget_mode),
        ("Stay", _text(trip.get("stay_type") or planning.get("stay_type"))),
        ("Local transport", ", ".join(_string_list(trip.get("local_transport") or planning.get("local_transport")))),
        ("Diet", _text(trip.get("diet") or planning.get("diet"))),
        ("Food styles", ", ".join(food_styles) or "No preference selected"),
        ("Date flexibility", date_flexibility),
        ("Travelling from", _text(trip.get("origin") or planning.get("origin"))),
        ("Arrival", _text(trip.get("arrival_mode") or planning.get("arrival_mode"))),
    ]


def _budget_page(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    summary = itinerary.get("budget_summary") or {}
    allocations = trip.get("budget_split") or summary.get("category_allocations") or summary.get("category_totals")
    allocations = allocations if isinstance(allocations, dict) else {}
    currency = _text(trip.get("currency") or itinerary.get("currency"))
    total = sum(_numeric(allocations.get(category)) or 0 for category in CATEGORIES)
    story: list[Any] = [
        Paragraph("Budget", styles["heading"]),
        Paragraph("Planning allocations only — these are not quoted or confirmed prices.", styles["body"]),
    ]
    present = [category for category in CATEGORIES if category in allocations]
    if present and total > 0:
        bar_widths = [width * (_numeric(allocations.get(category)) or 0) / total for category in present]
        bar = Table([[""] * len(present)], colWidths=bar_widths, rowHeights=[9])
        colors_by_category = {
            "stay": COBALT,
            "food": LATERITE,
            "transport": colors.HexColor("#0F8A7E"),
            "activities": colors.HexColor("#A87B05"),
            "misc": colors.HexColor("#6B7A90"),
        }
        bar.setStyle(
            TableStyle(
                [("BACKGROUND", (index, 0), (index, 0), colors_by_category[category]) for index, category in enumerate(present)]
                + [("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
            )
        )
        story.extend([Spacer(1, 4 * mm), bar, Spacer(1, 5 * mm)])

    rows = [[Paragraph("<b>Category</b>", styles["body"]), Paragraph("<b>Amount</b>", styles["body"]), Paragraph("<b>Share</b>", styles["body"])]]
    for category in CATEGORIES:
        amount = _numeric(allocations.get(category))
        value = _money(amount, currency) if amount is not None else "Not provided"
        share = f"{amount / total:.0%}" if amount is not None and total else "—"
        rows.append(
            [
                Paragraph(escape(category.title()), styles["body"]),
                Paragraph(escape(value), styles["body"]),
                Paragraph(escape(share), styles["small"]),
            ]
        )
    table = Table(rows, colWidths=[width * 0.42, width * 0.38, width * 0.2], hAlign="LEFT")
    table.setStyle(_card_table_style(header=True))
    story.extend([table, Spacer(1, 8 * mm)])
    budget_value = _money(trip.get("budget", itinerary.get("budget")), currency)
    story.append(Paragraph(f"Total trip budget: <b>{escape(budget_value)}</b>", styles["body"]))
    return story


def _day_page(
    trip: dict[str, Any],
    day: dict[str, Any],
    day_number: int,
    interests: list[str],
    assets: dict[str, dict[str, str]],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list[Any]:
    day_date = _text(day.get("date"))
    story: list[Any] = [
        Paragraph(f"DAY {day_number:02d}", styles["eyebrow"]),
        Paragraph(f"Day {day_number}" + (f" · {escape(day_date)}" if day_date else ""), styles["heading"]),
    ]
    weather = _day_weather(day)
    if weather:
        story.append(Paragraph(f"<b>Weather:</b> {escape(weather)}", styles["body"]))

    stops = [stop for stop in day.get("stops", []) if isinstance(stop, dict)]
    currency = _text(trip.get("currency") or (trip.get("itinerary") or {}).get("itinerary", {}).get("currency"))
    if stops:
        for stop in stops:
            place = str(stop.get("name") or "Place")
            asset = assets.get(_asset_key(place))
            photo = _image_flowable(asset, 39 * mm, 27 * mm) if asset else Spacer(39 * mm, 27 * mm)
            detail = [
                Paragraph(escape(place), styles["subheading"]),
            ]
            if stop.get("time"):
                detail.append(Paragraph(f"<b>{escape(str(stop['time']))}</b>", styles["small"]))
            if stop.get("notes"):
                detail.append(Paragraph(escape(str(stop["notes"])), styles["body"]))
            else:
                detail.append(Paragraph("No additional description was saved for this stop.", styles["small"]))
            cost = _money(stop.get("cost_estimate"), currency)
            detail.append(Paragraph(f"Estimated cost: <b>{escape(cost)}</b>", styles["cost"]))
            card = Table([[photo, detail]], colWidths=[42 * mm, width - 42 * mm], hAlign="LEFT")
            card.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend([card, Spacer(1, 4 * mm)])
    else:
        story.append(
            Paragraph(
                "Detailed stops were unavailable for this trip. No places or prices have been added.",
                styles["body"],
            )
        )
        if interests:
            story.append(Paragraph("Your saved interests", styles["subheading"]))
            interest_assets = [assets[_asset_key(interest)] for interest in interests if _asset_key(interest) in assets]
            if interest_assets:
                image_cells = [_image_flowable(asset, min(width / len(interest_assets), 52 * mm), 34 * mm) for asset in interest_assets]
                labels = [Paragraph(escape(interest), styles["center"]) for interest in interests if _asset_key(interest) in assets]
                image_table = Table([image_cells, labels], colWidths=[width / len(image_cells)] * len(image_cells))
                image_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.extend([image_table, Spacer(1, 4 * mm)])

    day_total = day.get("estimated_day_cost")
    if day_total is not None:
        story.append(
            Paragraph(f"Day total (priced items): <b>{escape(_money(day_total, currency))}</b>", styles["body"])
        )
    if day.get("notes"):
        story.append(Paragraph(escape(str(day["notes"])), styles["small"]))
    return story


def _closing_page(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    itinerary_result: dict[str, Any],
    credits: list[dict[str, str]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = [Paragraph("Notes &amp; credits", styles["heading"])]
    notes = _text(trip.get("notes") or itinerary.get("notes"))
    story.extend(
        [
            Paragraph("Your notes", styles["subheading"]),
            Paragraph(escape(notes) if notes else "No additional notes were saved for this trip.", styles["body"]),
        ]
    )
    warnings = itinerary.get("data_warnings") or []
    if not warnings and isinstance(itinerary_result, dict):
        tool_data = itinerary_result.get("tool_data") or {}
        warnings = [
            result.get("warning")
            for result in tool_data.values()
            if isinstance(result, dict) and result.get("warning")
        ]
    warnings = [str(value) for value in warnings if value]
    story.append(Paragraph("Travel data notes", styles["subheading"]))
    story.append(
        Paragraph(
            "<br/>".join(f"• {escape(warning)}" for warning in warnings)
            if warnings
            else "No data warnings were saved for this trip.",
            styles["body"],
        )
    )
    story.extend(
        [
            Paragraph("Please verify details before you travel", styles["subheading"]),
            Paragraph(
                "Prices and budget allocations are estimates or planning amounts, not confirmed quotes. "
                "Check opening hours, transport, availability, weather and current prices with the provider.",
                styles["body"],
            ),
            Paragraph("Image credits", styles["subheading"]),
        ]
    )
    if credits:
        for credit in credits:
            line = (
                f"{credit['title']} — {credit['author']}; {credit['license']}; "
                f"{credit['source']}"
            )
            if credit.get("credit_url"):
                line += f" ({credit['credit_url']})"
            story.append(Paragraph(escape(line), styles["small"]))
    else:
        story.append(Paragraph("No images were used.", styles["small"]))
    return story


def _fetch_images(requests: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    assets: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(requests)))) as executor:
        future_keys = {
            executor.submit(images.get_relevant_image, place_name, destination): key
            for key, (place_name, destination) in requests.items()
        }
        for future in as_completed(future_keys):
            key = future_keys[future]
            place_name, destination = requests[key]
            try:
                assets[key] = future.result()
            except Exception:
                logger.exception("Could not prepare PDF image for %s", place_name)
                assets[key] = images._placeholder(place_name or destination)
    return assets


def _image_credits(assets: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    credits = []
    seen = set()
    for asset in assets.values():
        credit = {key: asset.get(key, "") for key in ("title", "author", "license", "source", "credit_url")}
        key = tuple(credit.values())
        if key not in seen:
            seen.add(key)
            credits.append(credit)
    return credits


def _image_flowable(asset: dict[str, str], width: float, height: float) -> Image:
    raw = base64.b64decode(asset["image_base64"])
    with PILImage.open(io.BytesIO(raw)) as source:
        source = source.convert("RGB")
        target_ratio = width / height
        source_ratio = source.width / source.height
        if source_ratio > target_ratio:
            crop_width = int(source.height * target_ratio)
            left = (source.width - crop_width) // 2
            source = source.crop((left, 0, left + crop_width, source.height))
        else:
            crop_height = int(source.width / target_ratio)
            top = (source.height - crop_height) // 2
            source = source.crop((0, top, source.width, top + crop_height))
        source = source.resize((max(1, int(width * 2)), max(1, int(height * 2))), PILImage.Resampling.LANCZOS)
        output = io.BytesIO()
        source.save(output, format="JPEG", quality=80)
    return Image(io.BytesIO(output.getvalue()), width=width, height=height)


def _draw_page(canvas: Any, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, 14 * mm, page_width - document.rightMargin, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont(_FONT_REGULAR, 8)
    canvas.drawRightString(page_width - document.rightMargin, 9.5 * mm, f"Page {document.page}")
    canvas.restoreState()


def _card_table_style(header: bool = False) -> TableStyle:
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6FB")))
    return TableStyle(commands)


def _asset_key(name: str) -> str:
    return name.strip().casefold()


def _day_weather(day: dict[str, Any]) -> str:
    weather = _text(day.get("weather"))
    if not weather or weather.casefold() == "unavailable":
        return ""
    temperature = _text(day.get("temperature_range"))
    return " · ".join(value for value in (weather, temperature) if value)


def _date_range(trip: dict[str, Any], itinerary: dict[str, Any]) -> str:
    start = _text(trip.get("start_date") or itinerary.get("start_date"))
    end = _text(trip.get("end_date") or itinerary.get("end_date"))
    if not end and start:
        try:
            day_count = int(trip.get("days") or itinerary.get("days") or 0)
            if day_count > 0:
                end = (date.fromisoformat(start) + timedelta(days=day_count - 1)).isoformat()
        except (TypeError, ValueError):
            end = ""
    if start and end and end != start:
        return f"{start} – {end}"
    return start or end or "Dates not specified"


def _traveler_text(trip: dict[str, Any], itinerary: dict[str, Any]) -> str:
    travelers = trip.get("travelers") or (itinerary.get("planning_preferences") or {}).get("travelers")
    if isinstance(travelers, dict):
        parts = []
        adults = _numeric(travelers.get("adults"))
        children = _numeric(travelers.get("children"))
        if adults is not None:
            parts.append(f"{int(adults)} adult" + ("" if adults == 1 else "s"))
        if children:
            parts.append(f"{int(children)} child" + ("" if children == 1 else "ren"))
        if parts:
            group = _text(trip.get("group_type") or (itinerary.get("planning_preferences") or {}).get("group_type"))
            return ", ".join(parts) + (f" · {group}" if group else "")
    size = _numeric(trip.get("group_size"))
    return f"{int(size)} traveller" + ("" if size == 1 else "s") if size is not None else "Travellers not specified"


def _format_days(value: Any) -> str:
    days = _numeric(value)
    return f"{int(days)} day" + ("" if days == 1 else "s") if days is not None else "Not specified"


def _money(value: Any, currency: str) -> str:
    amount = _numeric(value)
    if amount is None:
        return "Not available"
    return f"{currency} {amount:,.2f}" if currency else f"{amount:,.2f}"


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "trip"
