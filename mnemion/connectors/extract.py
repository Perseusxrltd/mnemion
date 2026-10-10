"""Bounded Office text extraction. Macros, formulas and external links never run."""

import io
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from .providers import ProviderError


def spreadsheet(data: bytes) -> str:
    ns = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 100_000_000:
                raise ProviderError("spreadsheet_expansion_limit")
            if len({entry.filename for entry in entries}) != len(entries):
                raise ProviderError("ambiguous_spreadsheet")

            def xml(path):
                raw = archive.read(path)
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise ProviderError("spreadsheet_entities_not_allowed")
                return ET.fromstring(raw)

            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = [
                    "".join(item.itertext())
                    for item in xml("xl/sharedStrings.xml").findall("s:si", ns)
                ]
            relationships = {
                row.attrib["Id"]: row.attrib
                for row in xml("xl/_rels/workbook.xml.rels").findall("p:Relationship", ns)
            }
            sections = []
            for sheet in xml("xl/workbook.xml").findall("s:sheets/s:sheet", ns):
                relation = relationships[sheet.attrib["{" + ns["r"] + "}id"]]
                if relation.get("TargetMode") == "External":
                    raise ProviderError("spreadsheet_external_sheet_not_allowed")
                target = relation["Target"]
                path = posixpath.normpath(
                    target.lstrip("/") if target.startswith("/") else "xl/" + target
                )
                if not path.startswith("xl/") or "\\" in path:
                    raise ProviderError("invalid_spreadsheet_path")
                rows = ["# Sheet: " + sheet.attrib.get("name", "Sheet")]
                for row in xml(path).findall("s:sheetData/s:row", ns):
                    cells = []
                    for cell in row.findall("s:c", ns):
                        kind = cell.attrib.get("t")
                        value = cell.findtext("s:v", default="", namespaces=ns)
                        if kind == "s":
                            value = strings[int(value)]
                        elif kind == "inlineStr":
                            value = "".join(cell.find("s:is", ns).itertext())
                        formula = cell.findtext("s:f", default="", namespaces=ns)
                        if formula:
                            value += f" [formula: {formula}]"
                        if value:
                            cells.append(cell.attrib.get("r", "") + ": " + value)
                    if cells:
                        rows.append(" | ".join(cells))
                sections.append("\n".join(rows))
            return "\n\n".join(sections)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, IndexError, AttributeError):
        raise ProviderError("invalid_spreadsheet") from None
