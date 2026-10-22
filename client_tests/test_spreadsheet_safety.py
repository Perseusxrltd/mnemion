"""The same bounded spreadsheet format is accepted in supported XML encodings."""

import io
import zipfile

import pytest

from mnemion.connectors.extract import spreadsheet
from mnemion.connectors.providers import ProviderError


MEMBERS = {
    "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Décisions" r:id="one"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="one" Target="worksheets/sheet1.xml"/></Relationships>',
    "xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Café 漢字</t></si></sst>',
    "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>',
}


def workbook(encoding, declaration_member=None):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, xml in MEMBERS.items():
            declaration = "<!DOCTYPE fixture>" if name == declaration_member else ""
            label = "UTF-16BE" if encoding == "utf-16-be" else encoding
            body = f'<?xml version="1.0" encoding="{label}"?>{declaration}{xml}'
            archive.writestr(name, body.encode(encoding))
    return result.getvalue()


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-be"])
def test_supported_xml_encodings_preserve_unicode_and_inert_formula_text(encoding):
    result = spreadsheet(workbook(encoding))
    assert "# Sheet: Décisions" in result and "A1: Café 漢字" in result
    assert "B1: 2 [formula: 1+1]" in result


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-be"])
@pytest.mark.parametrize("member", MEMBERS)
def test_spreadsheet_declaration_policy_applies_to_every_xml_member(encoding, member):
    with pytest.raises(ProviderError, match="^spreadsheet_entities_not_allowed$"):
        spreadsheet(workbook(encoding, member))
