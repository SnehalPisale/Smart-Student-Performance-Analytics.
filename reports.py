"""Report datasets and CSV / Excel / PDF exports."""
import io
from datetime import datetime

import pandas as pd
from flask import Response

import analytics
import repository as repo

DATASETS = {
    "students": ("Student master list", ["usn", "name", "gender", "semester", "section", "email"]),
    "marks": ("Marks and attendance", ["usn", "name", "semester", "section", "subject_code",
                                        "internal1", "internal2", "assignment", "final_mark",
                                        "classes_held", "classes_attended", "attendance_pct"]),
    "predictions": ("Latest predictions", ["usn", "name", "semester", "section", "predicted_score",
                                            "risk_level", "avg_attendance", "avg_internal",
                                            "predicted_at"]),
    "at_risk": ("At-risk students", ["usn", "name", "semester", "section", "risk_level",
                                      "predicted_score", "avg_attendance", "reasons"]),
    "history": ("Prediction history", ["usn", "name", "predicted_score", "risk_level",
                                        "predicted_at"]),
}


def dataset(kind):
    title, cols = DATASETS[kind]
    if kind == "students":
        rows = [dict(r) for r in repo.list_students()]
    elif kind == "marks":
        rows = analytics.load_frame().to_dict("records")
    elif kind == "predictions":
        rows = analytics.prediction_table()
    elif kind == "at_risk":
        rows = [dict(p, reasons="; ".join(p["reasons"])) for p in analytics.prediction_table()
                if p["risk_level"] in ("High", "Medium")]
    else:
        rows = [dict(r) for r in repo.prediction_history(limit=5000)]
    return title, pd.DataFrame(rows, columns=cols)


def _safe(value):
    """Neutralise spreadsheet formula injection."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _clean(df):
    return df.apply(lambda col: col.map(_safe) if col.dtype == object else col)


def export(kind, fmt):
    title, df = dataset(kind)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = f"{kind}_{stamp}"
    df = _clean(df)
    if fmt == "csv":
        body = df.to_csv(index=False)
        return Response(body, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    if fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xl:
            df.to_excel(xl, index=False, sheet_name=kind[:30])
            ws = xl.sheets[kind[:30]]
            ws.freeze_panes = "A2"
            for i, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(str(x)) for x in df[col].head(200)]) + 2
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width, 50)
        return Response(buf.getvalue(),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    return Response(_pdf(title, df), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={name}.pdf"})


def _pdf(title, df):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24,
                            topMargin=28, bottomMargin=28, title=title)
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell")
    cell.fontSize, cell.leading = 7, 9
    head_style = cell.clone("head", textColor=colors.white)
    head = [Paragraph(f"<b>{c.replace('_', ' ').title()}</b>", head_style) for c in df.columns]
    body = [[Paragraph(_esc("" if pd.isna(v) else str(v)), cell) for v in row]
            for row in df.itertuples(index=False)]
    story = [Paragraph(title, styles["Title"]),
             Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M} - {len(df)} record(s)",
                       styles["Normal"]), Spacer(1, 10)]
    if body:
        table = Table([head] + body, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#26408B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8cedb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(table)
    else:
        story.append(Paragraph("No records to show.", styles["Normal"]))
    doc.build(story)
    return buf.getvalue()


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
