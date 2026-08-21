from dataclasses import dataclass

from app.documents.quotation_pdf import BasicQuotationPdfRenderer


@dataclass(frozen=True, slots=True)
class WorkflowPdfDocument:
    organization_name: str
    title: str
    document_number: str
    lines: tuple[str, ...]


class WorkflowPdfRenderer:
    """Small dependency-free renderer behind a replaceable document adapter."""

    def render(self, document: WorkflowPdfDocument) -> bytes:
        rows = [
            document.organization_name,
            document.title,
            document.document_number,
            "",
            *document.lines,
            "",
            "Generated from the approved, audited workflow record.",
        ]
        pages = [rows[index : index + 42] for index in range(0, len(rows), 42)]
        return BasicQuotationPdfRenderer()._build_pdf(pages)
