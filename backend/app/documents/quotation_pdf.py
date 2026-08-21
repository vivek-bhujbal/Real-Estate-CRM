from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class QuotationPdfLine:
    label: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class QuotationPdfDocument:
    organization_name: str
    quotation_number: str
    version: int
    customer_name: str
    project_name: str
    unit_number: str
    currency: str
    valid_until: str
    lines: tuple[QuotationPdfLine, ...]
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    final_agreed_value: Decimal
    booking_amount: Decimal


class QuotationPdfRenderer(Protocol):
    def render(self, document: QuotationPdfDocument) -> bytes: ...


def _escape(value: str) -> str:
    safe = value.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(currency: str, value: Decimal) -> str:
    return f"{currency} {value:,.2f}"


class BasicQuotationPdfRenderer:
    """Dependency-free PDF adapter; replace through the protocol for branded rendering."""

    lines_per_page = 42

    def render(self, document: QuotationPdfDocument) -> bytes:
        rows = [
            document.organization_name,
            "QUOTATION",
            f"{document.quotation_number}  |  Version {document.version}",
            "",
            f"Customer: {document.customer_name}",
            f"Project: {document.project_name}",
            f"Unit: {document.unit_number}",
            f"Valid until: {document.valid_until}",
            "",
            "COST BREAKDOWN",
        ]
        rows.extend(
            f"{line.label}: {_money(document.currency, line.amount)}" for line in document.lines
        )
        rows.extend(
            [
                "",
                f"Subtotal: {_money(document.currency, document.subtotal)}",
                f"Discount: {_money(document.currency, document.discount_amount)}",
                f"Taxes: {_money(document.currency, document.tax_amount)}",
                f"Final agreed value: {_money(document.currency, document.final_agreed_value)}",
                f"Booking amount: {_money(document.currency, document.booking_amount)}",
                "",
                "Generated from the immutable quotation pricing snapshot.",
            ]
        )
        pages = [
            rows[index : index + self.lines_per_page]
            for index in range(0, len(rows), self.lines_per_page)
        ]
        return self._build_pdf(pages)

    def _build_pdf(self, pages: list[list[str]]) -> bytes:
        page_ids = [4 + index * 2 for index in range(len(pages))]
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: (
                f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
                f"/Count {len(pages)} >>"
            ).encode("ascii"),
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        }
        for index, lines in enumerate(pages):
            page_id = page_ids[index]
            content_id = page_id + 1
            commands = ["BT", "/F1 10 Tf", "42 800 Td", "14 TL"]
            for line in lines:
                commands.append(f"({_escape(line)}) Tj")
                commands.append("T*")
            commands.append("ET")
            stream = "\n".join(commands).encode("latin-1")
            objects[page_id] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
            objects[content_id] = (
                f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
            )
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id in range(1, max(objects) + 1):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(objects[object_id])
            output.extend(b"\nendobj\n")
        xref = len(output)
        output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode(
                "ascii"
            )
        )
        return bytes(output)
