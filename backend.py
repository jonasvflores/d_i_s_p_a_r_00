import os
from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configurações
CHATWOOT_URL = "https://app.bee360.com.br/api/v1"
API_TOKEN = "e3nLN2WM3nsUbeM31BudDvit"  # Substitua pelo seu token
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"csv", "png", "jpg", "jpeg", "mp4", "mp3", "pdf"}

# Cabeçalhos corretos para token pessoal de agente
headers = {"api_access_token": API_TOKEN}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/accounts")
def get_accounts():
    # Simulando conta fixa, pois token de agente não acessa todas as contas
    return jsonify([{"id": 37, "name": "Archanjo.Co"}])

@app.route("/api/inboxes/<int:account_id>")
def get_inboxes(account_id):
    r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/inboxes", headers=headers)
    return jsonify(r.json())

@app.route("/api/labels/<int:account_id>")
def get_labels(account_id):
    r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/labels", headers=headers)
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

    # Busca contatos se for por etiqueta e não foram enviados via CSV
    if not contacts and label:
        r = requests.get(f"{CHATWOOT_URL}/accounts/{account_id}/contacts?labels={label}", headers=headers)
        if r.status_code == 200:
            contacts = r.json()["data"]
        else:
            return jsonify({"error": "Erro ao buscar contatos por etiqueta"}), 500

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

    return jsonify({"message": f"Disparo concluído! {enviados} de {total} mensagens enviadas."})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)