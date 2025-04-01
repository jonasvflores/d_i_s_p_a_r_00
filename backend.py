import os
from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3

app = Flask(__name__)

# Configurações
ACCOUNT_ID = 37  # Ajuste aqui para a conta desejada (ex.: 37)
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
    total INTEGER,
    tipo_disparo TEXT,
    order TEXT,
    saudacao TEXT,
    sair TEXT
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
        inboxes = [{"id": i["id"], "name": i["name"]} for i in r.json().get("data", {}).get("inboxes", [])]
        return jsonify(inboxes)
    return jsonify({"error": "Falha ao buscar inboxes"}), 500

@app.route("/api/labels")
def get_labels():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        labels = r.json().get("data", {}).get("labels", [])
        return jsonify(labels)
    return jsonify({"error": "Falha ao buscar etiquetas"}), 500

@app.route("/api/custom_attributes")
def get_custom_attributes():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        attrs = [{"key": attr["key"], "name": attr["name"]} for attr in r.json().get("data", {}).get("custom_attribute_definitions", [])]
        return jsonify(attrs)
    return jsonify({"error": "Falha ao buscar campos personalizados"}), 500

@app.route("/api/account_name")
def get_account_name():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        account_name = r.json().get("data", {}).get("account_name", "Conta não identificada")
        return jsonify({"account_name": account_name})
    return jsonify({"error": "Falha ao buscar nome da conta"}), 500

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
        file_url = f"http://localhost:5000/uploads/{filename}"  # Ajuste para um URL real em produção
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
        "body": data
    }
    
    if "contacts" in data:
        payload["body"]["contacts"] = data["contacts"]

    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        c.execute("INSERT INTO logs (timestamp, campaign, message, sent, total, tipo_disparo, order, saudacao, sair) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (datetime.now().isoformat(), data["campaign"], data["message"], 0, int(data["quantity"]) if data["quantity"] != "Todos" else 200,
                   data["tipo_disparo"], data["order"], data["saudacao"], data["sair"]))
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
        "total": r[5],
        "tipo_disparo": r[6],
        "order": r[7],
        "saudacao": r[8],
        "sair": r[9]
    } for r in rows])

@app.route("/api/campaigns/history/table")
def history_table():
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    html = """
    <
