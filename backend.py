import os
from flask import Flask, render_template, request, jsonify, send_from_directory
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3

app = Flask(__name__)

# Configurações
CHATWOOT_URL = "https://app.bee360.com.br/api/v1"
API_TOKEN = "e3nLN2WM3nsUbeM31BudDvit"  # Verifique se esse token tem acesso à conta 37
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"csv", "png", "jpg", "jpeg", "mp4", "mp3", "pdf"}

headers = {"api_access_token": API_TOKEN}

# Banco de dados para histórico
DB_PATH = "bee360_logs.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    campaign TEXT,
    message TEXT,
    sent INTEGER,
    total INTEGER
)''')
conn.commit()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/accounts")
def get_accounts():
    return jsonify([{"id": 37, "name": "Archanjo.Co"}])

@app.route("/api/inboxes/<int:account_id>")
def get_inboxes(account_id):
    r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/inboxes", headers=headers)
    if r.status_code != 200:
        print(f"Erro ao buscar inboxes: {r.status_code} - {r.text}")
        return jsonify([])
    return jsonify(r.json())

@app.route("/api/labels/<int:account_id>")
def get_labels(account_id):
    r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/labels", headers=headers)
    if r.status_code != 200:
        print(f"Erro ao buscar etiquetas: {r.status_code} - {r.text}")
        return jsonify([])
    return jsonify(r.json())

@app.route("/api/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("csvFile")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)
        try:
            df = pd.read_csv(path)
            if not {"nome", "telefone"}.issubset(df.columns):
                return jsonify({"error": "CSV precisa de colunas 'nome' e 'telefone'"})
            contatos = df[["nome", "telefone"]].to_dict(orient="records")
            return jsonify({"contacts": contatos})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Arquivo inválido"}), 400

@app.route("/api/upload_attachment", methods=["POST"])
def upload_attachment():
    file = request.files.get("attachment")
    account_id = request.form.get("account_id")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)
        r = requests.post(
            f"{CHATWOOT_URL}/accounts/{account_id}/attachments",
            headers=headers,
            files={"file": open(path, "rb")}
        )
        if r.status_code == 200:
            return jsonify({"attachment_id": r.json()["id"]})
        return jsonify({"error": "Falha ao enviar anexo"}), 500
    return jsonify({"error": "Arquivo inválido"}), 400

@app.route("/api/start_campaign", methods=["POST"])
def start_campaign():
    data = request.get_json()
    account_id = data.get("account_id")
    inbox_id = data.get("inbox_id")
    message = data.get("message")
    label = data.get("label")
    contacts = data.get("contacts", [])
    quantity = data.get("quantity")
    attachment_id = data.get("attachment_id")
    trigger = data.get("trigger_type", "etiquetas")
    campaign_name = data.get("campaign_name", "Sem Nome")

    if not contacts:
        if trigger == "etiquetas" and label:
            r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/contacts?labels={label}", headers=headers)
            if r.status_code == 200:
                contacts = r.json().get("data", [])
            else:
                print(f"Erro ao buscar contatos por etiqueta: {r.status_code} - {r.text}")
        elif trigger == "no_conversations":
            r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/contacts?sort=-created_at", headers=headers)
            if r.status_code == 200:
                contacts = [c for c in r.json().get("data", []) if c.get("conversations_count", 0) == 0]
        elif trigger == "no_interaction":
            r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/contacts?sort=last_activity_at", headers=headers)
            if r.status_code == 200:
                contacts = r.json().get("data", [])[::-1]

    total = len(contacts) if quantity == "Todos" else min(int(quantity), len(contacts))
    enviados = 0

    for contato in contacts[:total]:
        payload = {
            "inbox_id": inbox_id,
            "source_id": contato.get("phone_number") or contato.get("telefone"),
            "message": {
                "content": message.replace("{nome}", contato.get("name") or contato.get("nome", ""))
            }
        }
        if attachment_id:
            payload["message"]["attachment_ids"] = [attachment_id]

        r = requests.post(
            f"{CHATWOOT_URL}/accounts/{account_id}/conversations",
            headers=headers,
            json=payload
        )
        if r.status_code == 200:
            enviados += 1

    c.execute("INSERT INTO logs (timestamp, campaign, message, sent, total) VALUES (?, ?, ?, ?, ?)",
              (datetime.now().isoformat(), campaign_name, message, enviados, total))
    conn.commit()

    return jsonify({"message": f"Disparo concluído! {enviados} de {total} mensagens enviadas."})

@app.route("/api/campaigns/history")
def history():
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    return jsonify([{
        "id": r[0],
        "timestamp": r[1],
        "campaign": r[2],
        "message": r[3],
        "sent": r[4],
        "total": r[5]
    } for r in rows])

@app.route("/api/campaigns/history/table")
def history_table():
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    html = """
    <table border='1' cellpadding='6' cellspacing='0'>
        <thead>
            <tr><th>ID</th><th>Data</th><th>Campanha</th><th>Mensagem</th><th>Enviadas</th><th>Total</th></tr>
        </thead><tbody>
    """
    for r in rows:
        html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td></tr>"
    html += "</tbody></table>"
    return html

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
