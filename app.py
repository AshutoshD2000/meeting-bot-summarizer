from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import datetime
import requests
from dotenv import load_dotenv
import os
import json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter

load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "google/flan-t5-large"

app = Flask(__name__)

# ------------------ DATABASE INIT ------------------

def init_db():
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            meeting_type TEXT,
            transcript TEXT,
            summary TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------ SUMMARY LOGIC ------------------
def generate_summary(transcript):

    transcript_lower = transcript.lower()

    summary = f"This meeting discussed: {transcript[:150]}..."

    key_points = []
    decisions = []
    action_items = []
    agenda = []

    if "launch" in transcript_lower:
        key_points.append("Product launch discussed")
        decisions.append("Launch timeline planned")

    if "budget" in transcript_lower:
        key_points.append("Budget allocation reviewed")

    if "deadline" in transcript_lower or "march" in transcript_lower:
        key_points.append("Deadlines discussed")

    if "assign" in transcript_lower or "will" in transcript_lower:
        key_points.append("Tasks were assigned")

    if "marketing" in transcript_lower:
        agenda.append("Marketing Strategy")

    if not key_points:
        key_points.append("General project discussion")

    action_items.append({
        "task": "Review meeting outcomes",
        "owner": "Team",
        "due_date": "Next Meeting"
    })

    return {
        "summary": summary,
        "key_points": key_points,
        "decisions": decisions if decisions else ["No major decisions recorded"],
        "action_items": action_items,
        "agenda": agenda if agenda else ["General Discussion"]
    }

# ------------------ ROUTES ------------------

@app.route("/")
def home():
    return render_template("create_meeting.html")

@app.route("/create", methods=["POST"])
def create_meeting():

    title = request.form.get("title")
    meeting_type = request.form.get("type")
    transcript = request.form.get("transcript", "").strip()

    if not transcript:
        return render_template("create_meeting.html", error="Transcript is required.")

    ai_output = generate_summary(transcript)

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO meetings (title, meeting_type, transcript, summary, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        title,
        meeting_type,
        transcript,
        ai_output["summary"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    meeting_id = cursor.lastrowid
    conn.close()

    
    
    return render_template(
    "summary.html",
    title=title,
    meeting_type=meeting_type,
    data=ai_output,
    meeting_id=meeting_id   
)

@app.route("/history")
def history():
    search = request.args.get("search", "")
    meeting_type = request.args.get("type", "")

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    query = """
        SELECT id, title, meeting_type, created_at
        FROM meetings
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")

    if meeting_type:
        query += " AND meeting_type = ?"
        params.append(meeting_type)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    meetings = cursor.fetchall()
    conn.close()

    return render_template("history.html", meetings=meetings)

@app.route("/meeting/<int:meeting_id>")
def view_meeting(meeting_id):
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, meeting_type, transcript, summary, created_at
        FROM meetings
        WHERE id = ?
    """, (meeting_id,))

    meeting = cursor.fetchone()
    conn.close()

    return render_template(
    "view_meeting.html",
    meeting=meeting,
    meeting_id=meeting_id
)
from flask import Response

@app.route("/download/<int:meeting_id>")
def download_txt(meeting_id):

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, meeting_type, transcript, summary, created_at
        FROM meetings
        WHERE id = ?
    """, (meeting_id,))

    meeting = cursor.fetchone()
    conn.close()

    if not meeting:
        return "Meeting not found"

    title, meeting_type, transcript, summary_json, created_at = meeting

    try:
        data = json.loads(summary_json)
    except:
        data = {
        "summary": summary_json,
        "key_points": ["Data format issue"],
        "decisions": ["No decisions found"],
        "action_items": [
            {
                "task": "Review manually",
                "owner": "Team",
                "due_date": "Next Meeting"
            }
        ],
        "agenda": ["General Discussion"]
    }

    content = f"""
Meeting Title: {title}
Meeting Type: {meeting_type}
Date: {created_at}

SUMMARY:
{data['summary']}

KEY POINTS:
""" + "\n".join(f"- {kp}" for kp in data["key_points"]) + """

DECISIONS:
""" + "\n".join(f"- {d}" for d in data["decisions"]) + """

ACTION ITEMS:
""" + "\n".join(
        f"- {item['task']} (Owner: {item['owner']}, Due: {item['due_date']})"
        for item in data["action_items"]
    ) + """

AGENDA:
""" + "\n".join(f"- {a}" for a in data["agenda"])

    return Response(
        content,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f"attachment;filename={title}.txt"
        }
    )

@app.route("/delete/<int:meeting_id>")
def delete_meeting(meeting_id):
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    conn.commit()
    conn.close()

    return redirect("/history")

#---------------------jsoNAPI---------------------


@app.route("/meetings/<int:meeting_id>", methods=["GET"])
def api_get_meeting(meeting_id):

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, meeting_type, transcript, summary, created_at
        FROM meetings
        WHERE id = ?
    """, (meeting_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"error": "Meeting not found"}, 404

    # Safe JSON parsing
    try:
        summary_data = json.loads(row[3])
    except:
        summary_data = row[3]

    return {
        "title": row[0],
        "type": row[1],
        "transcript": row[2],
        "summary": summary_data,
        "created_at": row[4]
    }





@app.route("/meetings", methods=["GET"])
def api_get_meetings():
    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, meeting_type, created_at
        FROM meetings
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    meetings = []
    for row in rows:
        meetings.append({
            "id": row[0],
            "title": row[1],
            "type": row[2],
            "created_at": row[3]
        })

    return {"meetings": meetings}

@app.route("/meeting/create", methods=["POST"])
def api_create_meeting():
    data = request.json

    title = data.get("title")
    meeting_type = data.get("type")
    transcript = data.get("transcript")

    if not transcript:
        return {"error": "Transcript is required"}, 400

    ai_output = generate_summary(transcript)

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO meetings (title, meeting_type, transcript, summary, file_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        title,
        meeting_type,
        transcript,
        json.dumps(ai_output),
        None,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return {"message": "Meeting created", "data": ai_output}

from flask import send_file
import io

@app.route("/download/pdf/<int:meeting_id>")
def download_pdf(meeting_id):

    conn = sqlite3.connect("meetings.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, summary
        FROM meetings
        WHERE id = ?
    """, (meeting_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return "Meeting not found", 404

    title = row[0]

    try:
        summary_data = json.loads(row[1])
    except:
        summary_data = {"summary": row[1]}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(f"<b>{title}</b>", styles["Heading1"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(summary_data.get("summary", ""), styles["Normal"]))

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"meeting_{meeting_id}.pdf",
        mimetype="application/pdf"
    )



if __name__ == "__main__":
    app.run(debug=True)