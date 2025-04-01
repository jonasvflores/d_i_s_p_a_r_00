import os
from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3
import logging
import time

app = Flask(__name__)

# Configurações de logging para depuração
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configurações
ACCOUNT_ID = 58  # Ajuste aqui para a conta desejada (ex.: 58 para Atacadão Viana)
WEBHOOK_URL = "https://fluxo.archanjo.co/webhook/disparador-universal-bee360"
WEBHOOK_RESULT_URL = "https://fluxo.archanjo.co/webhook/disparador-universal-bee360/result"  # Ajuste para o endpoint correto
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
    "order" TEXT,
    saudacao TEXT,
    sair TEXT
)''')
conn.commit()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def poll_webhook_result(execution_id, max_attempts=10, delay=2):
    """Faz polling para obter o resultado do workflow do n8n."""
    for attempt in range(max_attempts):
        try:
            r = requests.get(f"{WEBHOOK_RESULT_URL}/{execution_id}")
            r.raise_for_status()
            response_data = r.json()
            logger.debug(f"Resultado do polling (tentativa {attempt + 1}): {response_data}")
            
            # Verifica se o workflow terminou e tem os dados esperados
            if response_data.get("status") == "completed" and "data" in response_data:
                return response_data["data"]
            elif response_data.get("status") == "failed":
                logger.error("Workflow falhou no n8n.")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao fazer polling: {str(e)}")
        
        time.sleep(delay)  # Espera antes da próxima tentativa
    
    logger.error("Timeout ao esperar o resultado do workflow.")
    return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/inboxes")
def get_inboxes():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    try:
        # Inicia o workflow
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        response_data = r.json()
        logger.debug(f"Resposta inicial do webhook para inboxes: {response_data}")
        
        # Verifica se o workflow foi iniciado e obtém o executionId
        if response_data.get("message") != "Workflow was started" or "executionId" not in response_data:
            logger.error("Resposta do webhook não contém executionId.")
            return jsonify({"error": "Falha ao iniciar o workflow"}), 500
        
        execution_id = response_data["executionId"]
        result_data = poll_webhook_result(execution_id)
        
        if not result_data:
            return jsonify({"error": "Falha ao obter inboxes"}), 500
        
        inboxes = result_data.get("inboxes", [])
        if not inboxes:
            logger.warning("Nenhuma inbox encontrada na resposta do webhook.")
            return jsonify({"error": "Nenhuma inbox encontrada"}), 500
        return jsonify(inboxes)
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar inboxes: {str(e)}")
        return jsonify({"error": "Falha ao buscar inboxes"}), 500

@app.route("/api/labels")
def get_labels():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    try:
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        response_data = r.json()
        logger.debug(f"Resposta inicial do webhook para labels: {response_data}")
        
        if response_data.get("message") != "Workflow was started" or "executionId" not in response_data:
            logger.error("Resposta do webhook não contém executionId.")
            return jsonify({"error": "Falha ao iniciar o workflow"}), 500
        
        execution_id = response_data["executionId"]
        result_data = poll_webhook_result(execution_id)
        
        if not result_data:
            return jsonify({"error": "Falha ao obter etiquetas"}), 500
        
        labels = result_data.get("labels", [])
        if not labels:
            logger.warning("Nenhuma etiqueta encontrada na resposta do webhook.")
            return jsonify({"error": "Nenhuma etiqueta encontrada"}), 500
        return jsonify(labels)
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar etiquetas: {str(e)}")
        return jsonify({"error": "Falha ao buscar etiquetas"}), 500

@app.route("/api/custom_attributes")
def get_custom_attributes():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    try:
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        response_data = r.json()
        logger.debug(f"Resposta inicial do webhook para custom_attributes: {response_data}")
        
        if response_data.get("message") != "Workflow was started" or "executionId" not in response_data:
            logger.error("Resposta do webhook não contém executionId.")
            return jsonify({"error": "Falha ao iniciar o workflow"}), 500
        
        execution_id = response_data["executionId"]
        result_data = poll_webhook_result(execution_id)
        
        if not result_data:
            return jsonify({"error": "Falha ao obter campos personalizados"}), 500
        
        attrs = [{"key": attr["key"], "name": attr["name"]} for attr in result_data.get("custom_attribute_definitions", [])]
        if not attrs:
            logger.warning("Nenhum campo personalizado encontrado na resposta do webhook.")
            return jsonify({"error": "Nenhum campo personalizado encontrado"}), 500
        return jsonify(attrs)
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar campos personalizados: {str(e)}")
        return jsonify({"error": "Falha ao buscar campos personalizados"}), 500

@app.route("/api/account_name")
def get_account_name():
    payload = {"query": {"account_id": ACCOUNT_ID}}
    try:
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        response_data = r.json()
        logger.debug(f"Resposta inicial do webhook para account_name: {response_data}")
        
        if response_data.get("message") != "Workflow was started" or "executionId" not in response_data:
            logger.error("Resposta do webhook não contém executionId.")
            return jsonify({"error": "Falha ao iniciar o workflow"}), 500
        
        execution_id = response_data["executionId"]
        result_data = poll_webhook_result(execution_id)
        
        if not result_data:
            return jsonify({"error": "Falha ao obter nome da conta"}), 500
        
        account_name = result_data.get("account_name", "Conta não identificada")
        if account_name == "Conta não identificada":
            logger.warning("Nome da conta não encontrado na resposta do webhook.")
        return jsonify({"account_name": account_name})
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar nome da conta: {str(e)}")
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
        base_url = request Oldals.request.host_url.rstrip('/')
        file_url = f"{base_url}/uploads/{filename}"
        return jsonify({"file_url": file_url})
    return jsonify({"error": "Arquivo inválido"}), 400

@app.route("/uploads/<filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

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

    try:
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        c.execute('INSERT INTO logs (timestamp, campaign, message, sent, total, tipo_disparo, "order", saudacao, sair) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (datetime.now().isoformat(), data["campaign"], data["message"], 0, int(data["quantity"]) if data["quantity"] != "Todos" else 200,
                   data["tipo_disparo"], data["order"], data["saudacao"], data["sair"]))
        conn.commit()
        return jsonify({"message": "Campanha iniciada! Aguarde o processamento no n8n."})
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao iniciar campanha: {str(e)}")
        return jsonify({"error": "Falha ao iniciar campanha"}), 500

@app.route("/api/campaigns/history")
def history():
    c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 20')
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
    c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 20')
    rows = c.fetchall()
    html = """
    <table border='1' cellpadding='6' cellspacing='0'>
        <thead>
            <tr><th>ID</th><th>Data</th><th>Campanha</th><th>Mensagem</th><th>Enviadas</th><th>Total</th><th>Tipo</th></tr>
        </thead><tbody>
    """
    for r in rows:
        html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td><td>{r[6]}</td></tr>"
    html += "</tbody></table>"
    return html

@app.route("/api/campaigns/last")
def last_campaign():
    c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    if row:
        return jsonify({
            "campaign": row[2],
            "message": row[3],
            "quantity": str(row[5]),
            "tipo_disparo": row[6],
            "order": row[7],
            "saudacao": row[8],
            "sair": row[9]
        })
    return jsonify({"error": "Nenhuma campanha encontrada"}), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
