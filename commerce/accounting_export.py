"""Small dependency-free XLSX exporter; all values come from the report service."""
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
import re

from django.http import HttpResponse

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def column_name(number):
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xml(element):
    return tostring(element, encoding="utf-8", xml_declaration=True)


HEADER_ROW = 7


def workbook_bytes(sheets, *, introduction=(), bands=()):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        content = Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
        for extension, kind in (("rels", "application/vnd.openxmlformats-package.relationships+xml"), ("xml", "application/xml")):
            SubElement(content, "Default", Extension=extension, ContentType=kind)
        root_rel = Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        SubElement(root_rel, "Relationship", Id="rId1", Type=REL + "/officeDocument", Target="xl/workbook.xml")
        archive.writestr("_rels/.rels", xml(root_rel))
        book = Element("workbook", xmlns=NS, attrib={"xmlns:r": REL})
        book_sheets = SubElement(book, "sheets")
        relationships = Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        for i, (name, headers, rows) in enumerate(sheets, 1):
            SubElement(book_sheets, "sheet", name=name, sheetId=str(i), attrib={"r:id": f"rId{i}"})
            SubElement(relationships, "Relationship", Id=f"rId{i}", Type=REL + "/worksheet", Target=f"worksheets/sheet{i}.xml")
            SubElement(content, "Override", PartName=f"/xl/worksheets/sheet{i}.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
            sheet = Element("worksheet", xmlns=NS)
            properties = SubElement(sheet, "sheetPr")
            SubElement(properties, "pageSetUpPr", fitToPage="1")
            views = SubElement(sheet, "sheetViews")
            view = SubElement(views, "sheetView", workbookViewId="0", showGridLines="0", zoomScale="85")
            SubElement(view, "pane", xSplit="4", ySplit=str(HEADER_ROW), topLeftCell="E8", activePane="bottomRight", state="frozen")
            SubElement(view, "selection", pane="bottomRight", activeCell="E8", sqref="E8")
            cols = SubElement(sheet, "cols")
            widths = (21, 27, 38, 24, 12, 17, 17, 18, 18, 23, 23, 18, 18, 16, 21, 17)
            for j, header in enumerate(headers, 1):
                SubElement(cols, "col", min=str(j), max=str(j), width=str(widths[j - 1]), customWidth="1")
            data = SubElement(sheet, "sheetData")
            prefix = [[value] for value in introduction]
            prefix += [[] for _ in range(HEADER_ROW - 1 - len(prefix))]
            last_row = HEADER_ROW + len(rows)
            for row_index, values in enumerate([*prefix, headers, *rows], 1):
                is_header = row_index == HEADER_ROW
                is_total = row_index == last_row
                data_index = row_index - HEADER_ROW - 1
                shaded = 0 <= data_index < len(bands) and bands[data_index] % 2 == 1
                height = 34 if row_index == 1 else (54 if is_header else (32 if row_index < HEADER_ROW else 36))
                row = SubElement(data, "row", r=str(row_index), ht=str(height), customHeight="1")
                for j, value in enumerate(values, 1):
                    numeric = isinstance(value, (Decimal, int)) and not isinstance(value, bool)
                    if row_index < HEADER_ROW:
                        style = 3 if row_index == 1 else 4
                    elif is_header:
                        style = 1
                    elif is_total:
                        style = 8 if isinstance(value, Decimal) else 7
                    elif isinstance(value, Decimal):
                        style = 6 if shaded else 2
                    elif numeric:
                        style = 10 if shaded else 9
                    else:
                        style = 5 if shaded else 0
                    node = SubElement(row, "c", r=f"{column_name(j)}{row_index}",
                                      s=str(style),
                                      t="n" if numeric else "inlineStr")
                    if value is None:
                        node.attrib.pop("t")
                    elif numeric:
                        SubElement(node, "v").text = str(value)
                    else:
                        # Explicit inline text, never a formula, including = + - @.
                        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))[:32767]
                        SubElement(SubElement(node, "is"), "t", attrib={"xml:space": "preserve"}).text = text
            # Summary stays outside the filter so sorting/filtering cannot treat it as a sale.
            SubElement(sheet, "autoFilter", ref=f"A{HEADER_ROW}:{column_name(len(headers))}{max(HEADER_ROW, last_row - 1)}")
            merges = SubElement(sheet, "mergeCells", count=str(len(introduction)))
            for row_index in range(1, len(introduction) + 1):
                SubElement(merges, "mergeCell", ref=f"A{row_index}:{column_name(len(headers))}{row_index}")
            SubElement(sheet, "printOptions", horizontalCentered="1")
            SubElement(sheet, "pageMargins", left="0.25", right="0.25", top="0.4", bottom="0.4", header="0.2", footer="0.2")
            SubElement(sheet, "pageSetup", paperSize="8", orientation="landscape", fitToWidth="1", fitToHeight="0")
            footer = SubElement(sheet, "headerFooter")
            SubElement(footer, "oddFooter").text = "&LFlexDrive&C&A&R&P / &N"
            archive.writestr(f"xl/worksheets/sheet{i}.xml", xml(sheet))
        definitions = SubElement(book, "definedNames")
        for index, (name, headers, rows) in enumerate(sheets):
            quoted = "'" + name.replace("'", "''") + "'"
            SubElement(definitions, "definedName", name="_xlnm.Print_Titles", localSheetId=str(index)).text = f"{quoted}!$1:${HEADER_ROW}"
            SubElement(definitions, "definedName", name="_xlnm.Print_Area", localSheetId=str(index)).text = f"{quoted}!$A$1:${column_name(len(headers))}${HEADER_ROW + len(rows)}"
        for part, kind in (("workbook.xml", "sheet.main"), ("styles.xml", "styles")):
            SubElement(content, "Override", PartName="/xl/" + part, ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml")
        SubElement(relationships, "Relationship", Id="styles", Type=REL + "/styles", Target="styles.xml")
        archive.writestr("[Content_Types].xml", xml(content))
        archive.writestr("xl/workbook.xml", xml(book))
        archive.writestr("xl/_rels/workbook.xml.rels", xml(relationships))
        archive.writestr("xl/styles.xml", styles_xml())
    return output.getvalue()


def styles_xml():
    styles = Element("styleSheet", xmlns=NS)
    formats = SubElement(styles, "numFmts", count="1")
    SubElement(formats, "numFmt", numFmtId="164", formatCode='#,##0.00;[Red](#,##0.00);0.00')
    fonts = SubElement(styles, "fonts", count="3")
    for size, color, bold in ((10, "FF203547", False), (10, "FFFFFFFF", True), (18, "FFFFFFFF", True)):
        font = SubElement(fonts, "font")
        if bold:
            SubElement(font, "b")
        SubElement(font, "sz", val=str(size))
        SubElement(font, "color", rgb=color)
        SubElement(font, "name", val="Calibri")
    fills = SubElement(styles, "fills", count="4")
    for pattern, color in (("none", None), ("gray125", None), ("solid", "FF173B55"), ("solid", "FFF0F5F9")):
        fill = SubElement(SubElement(fills, "fill"), "patternFill", patternType=pattern)
        if color:
            SubElement(fill, "fgColor", rgb=color)
            SubElement(fill, "bgColor", indexed="64")
    borders = SubElement(styles, "borders", count="1")
    SubElement(borders, "border")
    base = SubElement(styles, "cellStyleXfs", count="1")
    SubElement(base, "xf", numFmtId="0", fontId="0", fillId="0", borderId="0")
    xfs = SubElement(styles, "cellXfs", count="11")
    for font, fill, number in ((0,0,0),(1,2,0),(0,0,164),(2,2,0),(0,0,0),
                               (0,3,0),(0,3,164),(1,2,0),(1,2,164),(0,0,3),(0,3,3)):
        xf = SubElement(xfs, "xf", fontId=str(font), fillId=str(fill), numFmtId=str(number),
                        borderId="0", xfId="0", applyAlignment="1", applyNumberFormat="1", applyFill="1", applyFont="1")
        SubElement(xf, "alignment", vertical="center", horizontal="right" if number else "left", wrapText="1")
    names = SubElement(styles, "cellStyles", count="1")
    SubElement(names, "cellStyle", name="Normal", xfId="0", builtinId="0")
    return xml(styles)


def export_response(report):
    period = report["period"]
    name = {"paid": "წარმატებული", "refunded": "დაბრუნებული", "all": "ყველა"}[report["status"]]
    rows = report["rows"] + [report["totals"]]
    introduction = ["FlexDrive — ბუღალტრული ანგარიშგება",
        f"პერიოდი: {period.start:%d.%m.%Y} — {period.end:%d.%m.%Y}  |  {name}  |  {report['order_count']} შეკვეთა",
        f"პროდუქტის სახელი / SKU: {report.get('sku') or 'ყველა პროდუქტი'}",
        "თანხები: ლარი (GEL)  •  დღგ: 18%  •  დრო: თბილისი  •  პროდუქტის მოგება სხვა ხარჯების გამოკლებამდეა.",
        ("ძიებისას მიტანა და სრული თანხა პროდუქტზე არ ნაწილდება. " if report.get("sku") else "მიტანა და სრული თანხა თითო შეკვეთაზე ერთხელაა. ")
        + ("დაბრუნებები უარყოფითია; ჯამში აკლდება გადახდებს." if report["status"] == "all" else
           "თარიღები დაბრუნების დადასტურებით." if report["status"] == "refunded" else "თარიღები გადახდის დადასტურებით; დაბრუნებული შეკვეთები გამორიცხულია.")]
    bands = [index for index, group in enumerate(report["groups"]) for _ in group["rows"]]
    response = HttpResponse(workbook_bytes([(name, report["headers"], rows)], introduction=introduction, bands=bands),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="FlexDrive-{report["status"]}-{period.start}-{period.end}.xlsx"'
    return response
