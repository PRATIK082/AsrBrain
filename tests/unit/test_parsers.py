import os

import pytest

from src.ingestion.parsers import get_parser, parser_quality_report
from src.ingestion.pdf_extract import sha256_file


@pytest.mark.skipif(
    not os.path.exists("pdf/AUTOSAR_FO_PRS_SOMEIPProtocol.pdf"),
    reason="SOME/IP PRS PDF not present (optional fixture)",
)
def test_adapter_extracts_tables_and_figures():
    pages = get_parser("auto").parse("pdf/AUTOSAR_FO_PRS_SOMEIPProtocol.pdf")
    assert len(pages) > 50
    assert sum(len(p.tables) for p in pages) >= 1
    assert sum(len(p.figures) for p in pages) >= 1
    qr = parser_quality_report(pages, "pdf/AUTOSAR_FO_PRS_SOMEIPProtocol.pdf", sha256_file("pdf/AUTOSAR_FO_PRS_SOMEIPProtocol.pdf"))
    assert qr["tables_detected"] >= 1 and "quality_score" in qr
