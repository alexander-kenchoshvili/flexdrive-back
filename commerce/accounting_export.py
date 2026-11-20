"""Small dependency-free XLSX exporter; all values come from the report service."""
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
import re

from django.http import HttpResponse
from .accounting_ledger import HEADERS, visible_columns
from .accounting_reports import TBILISI
from .accounting_buyers import BUYER_COLUMNS

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


def workbook_bytes(sheets, *, introduction=(), bands=(), introductions=None, detail_sheets=()):
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
            sheet_introduction = (introductions or {}).get(name, introduction)
            SubElement(book_sheets, "sheet", name=name, sheetId=str(i), attrib={"r:id": f"rId{i}"})
            SubElement(relationships, "Relationship", Id=f"rId{i}", Type=REL + "/worksheet", Target=f"worksheets/sheet{i}.xml")
            SubElement(content, "Override", PartName=f"/xl/worksheets/sheet{i}.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
            sheet = Element("worksheet", xmlns=NS)
            properties = SubElement(sheet, "sheetPr")
            SubElement(properties, "pageSetUpPr", fitToPage="1")
            views = SubElement(sheet, "sheetViews")
            view = SubElement(views, "sheetView", workbookViewId="0", showGridLines="0", zoomScale="85")
            first_scroll_cell = "B8" if name in detail_sheets else "E8"
            SubElement(view, "pane", xSplit="1" if name in detail_sheets else "4", ySplit=str(HEADER_ROW),
                       topLeftCell=first_scroll_cell, activePane="bottomRight", state="frozen")
            SubElement(view, "selection", pane="bottomRight", activeCell=first_scroll_cell, sqref=first_scroll_cell)
            cols = SubElement(sheet, "cols")
            widths = (21, 27, 38, 24, 12, 17, 17, 18, 18, 23, 23, 18, 18, 16, 21, 17)
            width_by_header = dict(zip(HEADERS, (*widths, 23, 30)))
            if name in detail_sheets:
                width_by_header.update({label: width for _, label, width in BUYER_COLUMNS})
            for j, header in enumerate(headers, 1):
                SubElement(cols, "col", min=str(j), max=str(j), width=str(width_by_header.get(header, 20)), customWidth="1")
            data = SubElement(sheet, "sheetData")
            prefix = [[value] for value in sheet_introduction]
            prefix += [[] for _ in range(HEADER_ROW - 1 - len(prefix))]
            last_row = HEADER_ROW + len(rows)
            for row_index, values in enumerate([*prefix, headers, *rows], 1):
                is_header = row_index == HEADER_ROW
                is_total = row_index == last_row and name not in detail_sheets
                data_index = row_index - HEADER_ROW - 1
                shaded = 0 <= data_index < len(bands) and bands[data_index] % 2 == 1
                if name in detail_sheets:
                    shaded = data_index >= 0 and data_index % 2 == 1
                height = 34 if row_index == 1 else (54 if is_header else (32 if row_index < HEADER_ROW else
                         48 if name in detail_sheets else 36))
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
                    elif name in detail_sheets:
                        style = 12 if shaded else 11  # Explicit Excel text format retains leading zeroes.
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
            filter_end = last_row if name in detail_sheets else last_row - 1
            SubElement(sheet, "autoFilter", ref=f"A{HEADER_ROW}:{column_name(len(headers))}{max(HEADER_ROW, filter_end)}")
            merges = SubElement(sheet, "mergeCells", count=str(len(sheet_introduction)))
            for row_index in range(1, len(sheet_introduction) + 1):
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
    xfs = SubElement(styles, "cellXfs", count="13")
    for font, fill, number in ((0,0,0),(1,2,0),(0,0,164),(2,2,0),(0,0,0),
                               (0,3,0),(0,3,164),(1,2,0),(1,2,164),(0,0,3),(0,3,3),(0,0,49),(0,3,49)):
        xf = SubElement(xfs, "xf", fontId=str(font), fillId=str(fill), numFmtId=str(number),
                        borderId="0", xfId="0", applyAlignment="1", applyNumberFormat="1", applyFill="1", applyFont="1")
        SubElement(xf, "alignment", vertical="center", horizontal="right" if number and number != 49 else "left", wrapText="1")
    names = SubElement(styles, "cellStyles", count="1")
    SubElement(names, "cellStyle", name="Normal", xfId="0", builtinId="0")
    return xml(styles)


def export_response(report):
    period = report["period"]
    name = {"paid": "წარმატებული", "refunded": "დაბრუნებული", "all": "ყველა"}[report["status"]]
    columns = visible_columns(report.get("show_purchase", False))
    headers = [report["headers"][i] for i in columns]
    rows = [[row[i] for i in columns] for row in report["rows"] + [report["totals"]]]
    introduction = ["FlexDrive — ბუღალტრული ანგარიშგება",
        f"პერიოდი: {period.start:%d.%m.%Y} — {period.end:%d.%m.%Y}  |  {name}  |  {report['order_count']} შეკვეთა",
        f"პროდუქტის სახელი / SKU: {report.get('sku') or 'ყველა პროდუქტი'}",
        "თანხები: ლარი (GEL)  •  დღგ: 18%  •  დრო: თბილისი  •  პროდუქტის მოგება სხვა ხარჯების გამოკლებამდეა.",
        ("ძიებისას მიტანა და სრული თანხა პროდუქტზე არ ნაწილდება. " if report.get("sku") else "მიტანა და სრული თანხა თითო შეკვეთაზე ერთხელაა. ")
        + ("დაბრუნებები უარყოფითია; ჯამში აკლდება გადახდებს." if report["status"] == "all" else
           "თარიღები დაბრუნების დადასტურებით." if report["status"] == "refunded" else "თარიღები გადახდის დადასტურებით; დაბრუნებული შეკვეთები გამორიცხულია.")]
    bands = [index for index, group in enumerate(report["groups"]) for _ in group["rows"]]
    sheets = [(name, headers, rows)]
    costs = report.get("return_costs")
    if costs is not None:
        cost_rows = [[row["recorded_at"].astimezone(TBILISI).strftime("%d.%m.%Y %H:%M"),
                      row["order_number"], row["cost"]] for row in costs["rows"]]
        cost_rows.append(["სულ — დაფიქსირების თარიღით", None, costs["total"]])
        sheets.append(("უკუმიტანის ხარჯი", ["ხარჯის დაფიქსირების დრო", "შეკვეთა", "უკუმიტანის ხარჯი ₾"], cost_rows))
    cost_introduction = ["FlexDrive — უკუმიტანის ხარჯები", f"პერიოდი: {period.start:%d.%m.%Y} — {period.end:%d.%m.%Y}",
        "ხარჯის დაფიქსირების თარიღით; ბანკის დაბრუნების შედეგისგან დამოუკიდებლად.",
        "ოპერატორის დაფიქსირებული თანხები ლარში; ინვოისის გადახდას არ ადასტურებს.",
        "უცნობი ხარჯი ნულის ნაცვლად ცარიელია; ასეთ შემთხვევაში სრული ჯამიც უცნობია."]
    introductions = {"უკუმიტანის ხარჯი": cost_introduction}
    buyers = report.get("buyers", [])
    sheets.append(("მყიდველები", [label for _, label, _ in BUYER_COLUMNS],
                   [[buyer[key] or None for key, _, _ in BUYER_COLUMNS] for buyer in buyers]))
    introductions["მყიდველები"] = ["FlexDrive — მყიდველის მონაცემები", introduction[1], introduction[2],
        "შეკვეთაზე შენახული მონაცემები ზედნადების მოსამზადებლად; თითო შეკვეთაზე ერთი ჩანაწერია.",
        "ცარიელი ველი ნიშნავს, რომ მონაცემი არ არის შენახული ან ამ ტიპის მყიდველს არ ეხება."]
    bookings = report.get("courier_bookings")
    if bookings is not None and bookings["rows"]:
        booking_rows = [[row["date"], row["order_number"], row["stage_label"], Decimal(row["customer_delivery"]),
            Decimal(row["quoted_price"]), Decimal(row["booked_price"]) if row["booked_price"] is not None else None,
            Decimal(row["buffer"]), Decimal(row["difference"]) if row["difference"] is not None else None] for row in bookings["rows"]]
        booking_rows.append(["სულ — გაუქმებულის გარეშე", None, None, None, None, bookings["total"], None, bookings["difference"]])
        sheets.append(("Wingo გზავნილები", ["შექმნის თარიღი", "შეკვეთა", "მდგომარეობა", "მომხმარებლის მიტანის თანხა ₾",
            "ჩექაუთის ტარიფი ₾", "Wingo-ს ფასი ₾", "ბუფერი ₾", "ფასთა სხვაობა ₾"], booking_rows))
        introductions["Wingo გზავნილები"] = ["FlexDrive — Wingo-ს გზავნილების ფასები", introduction[1],
            "გზავნილის შექმნის თარიღით; ინვოისის ნაშთს ან ხარჯის გადახდას არ ადასტურებს.",
            "გაუქმებული გზავნილები ჯამში არ შედის; შესაძლო საკურიერო ხარჯი ცალკე შესაჯერებელია.",
            "უცნობი ფასი ცარიელია და სრულ ჯამს უცნობს ტოვებს."]
    response = HttpResponse(workbook_bytes(sheets, introduction=introduction, bands=bands,
                            introductions=introductions, detail_sheets={"მყიდველები"}),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="FlexDrive-{report["status"]}-{period.start}-{period.end}.xlsx"'
    return response
