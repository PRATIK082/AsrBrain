"""Version-specific fixtures: same requirement text under two releases must not mix."""
CLASSIC_42 = {"chunk_id": "c42", "document_id": "d", "source_pdf": "SWS_CanIf_4.2.2.pdf",
              "page_start": 10, "page_end": 10, "autosar_release": "4.2.2", "platform": "Classic",
              "module": "CanIf", "document_type": "SWS", "section_number": "7.1", "section_title": "Init",
              "requirement_ids": ["SWS_CANIF_00001"], "api_names": ["CanIf_Init"],
              "normalized_text": "CanIf_Init shall initialize in 4.2", "compressed": "CanIf_Init shall initialize in 4.2"}
CLASSIC_44 = {"chunk_id": "c44", "document_id": "d", "source_pdf": "SWS_CanIf_4.4.0.pdf",
              "page_start": 12, "page_end": 12, "autosar_release": "4.4.0", "platform": "Classic",
              "module": "CanIf", "document_type": "SWS", "section_number": "7.1", "section_title": "Init",
              "requirement_ids": ["SWS_CANIF_00001"], "api_names": ["CanIf_Init"],
              "normalized_text": "CanIf_Init shall initialize in 4.4 with extra check", "compressed": "CanIf_Init shall initialize in 4.4"}
