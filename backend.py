import os
from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3

app = Flask(__name__)

# Configurações
ACCOUNT_ID = 58  # Ajuste conforme necessário
WEBHOOK_URL = "https://fluxo.archanjo.co/webhook/disparador-universal-bee360"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"csv", "png", "jpg", "jpeg", "mp4", "mp3", "pdf"}

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

@app.route("/api/inboxes")
def get_inboxes():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        # Simulando resposta baseada no n8n (ajuste conforme o retorno real)
        inboxes = [{"id": i["id"], "name": i["name"]} for i in requests.get(f"https://app.bee360.com.br/api/v1/accounts/{ACCOUNT_ID}/inboxes", headers={"api_access_token": "SEU_TOKEN"}).json()]
        return jsonify(inboxes)
    return jsonify({"error": "Falha ao buscar inboxes"}), 500

@app.route("/api/labels")
def get_labels():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        # Simulando resposta (ajuste com base no n8n ou API direta)
        labels = requests.get(f"https://app.bee360.com.br/api/v1/accounts/{ACCOUNT_ID}/labels", headers={"api_access_token": "SEU_TOKEN"}).json()
        return jsonify(labels)
    return jsonify({"error": "Falha ao buscar etiquetas"}), 500

@app.route("/api/account_name")
def get_account_name():
    return jsonify({"account_name": "Atacadão Viana"})  # Ajuste para buscar dinamicamente se necessário

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
                return jsonify({"error": "CSV precisa de colunas 'nome' e 'telefone'"}), 400
            contacts = df[["nome", "telefone"]].to_dict(orient="records")
            return jsonify({"contacts": contacts})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Arquivo inválido"}), 400

@app.route("/api/upload_attachment", methods=["POST"])
def upload_attachment():
    file = request.files.get("attachment")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)
        # Aqui você pode subir o arquivo para um serviço como S3 ou retornar o caminho local
        file_url = f"http://localhost:5000/uploads/{filename}"  # Ajuste para um URL real
        return jsonify({"file_url": file_url})
    return jsonify({"error": "Arquivo inválido"}), 400

@app.route("/api/start_campaign", methods=["POST"])
def start_campaign():
    data = request.get_json()
    payload = {
        "query": {
            "account_id": data["account_id"],
            "inbox": data["inbox"],
            "campaign": data["campaign"],
            "message": data["message"],
            "quantity": data["quantity"],
            "tipo_disparo": data["tipo_disparo"],
            "label": data.get("label", ""),
            "fileUrl": data.get("fileUrl", ""),
            "custom_attribute_filter": data.get("custom_attribute_filter", ""),
            "text_custom_attribute_filter": data.get("text_custom_attribute_filter", ""),
            "date_limit": data.get("date_limit", ""),
            "order": data["order"],
            "saudacao": data["saudacao"],
            "sair": data["sair"]
        },
        "body": data  # Inclui todos os dados no body também, como no Typebot
    }
    
    if "contacts" in data:
        payload["body"]["contacts"] = data["contacts"]

    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        c.execute("INSERT INTO logs (timestamp, campaign, message, sent, total) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().isoformat(), data["campaign"], data["message"], 0, int(data["quantity"]) if data["quantity"] != "Todos" else 200))
        conn.commit()
        return jsonify({"message": "Campanha iniciada! Aguarde o processamento no n8n."})
    return jsonify({"error": "Falha ao iniciar campanha"}), 500

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

@app.route("/api/campaigns/last")
def last_campaign():
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row:
        return jsonify({
            "campaign": row[2],
            "message": row[3],
            "quantity": str(row[5]),
            "tipo_disparo": "Disparo condicional por etiquetas"  # Ajuste conforme necessário
        })
    return jsonify({"error": "Nenhuma campanha encontrada"}), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
