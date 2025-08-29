import os, json, requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

# Variáveis de ambiente (vamos configurar no Render)
VERIFY_TOKEN   = os.environ["WHATSAPP_VERIFY_TOKEN"]   # ex.: verifyJR2025
WABA_PHONE_ID  = os.environ["WABA_PHONE_ID"]           # ex.: 778846328642993
WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]          # token da Meta

# Função para enviar mensagem de texto pelo WhatsApp
def send_text(to: str, body: str):
    url = f"https://graph.facebook.com/v20.0/{WABA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception:
        pass

# Webhook de verificação (Meta chama quando configuramos o callback)
@app.get("/webhook")
def verify(mode: str = "", challenge: str = "", token: str = ""):
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge, status_code=200)
    return PlainTextResponse("forbidden", status_code=403)

# Webhook para receber mensagens
@app.post("/webhook")
async def incoming(req: Request):
    data = await req.json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages", [])
        if not messages:
            return {"ok": True}

        msg = messages[0]
        from_number = msg.get("from", "")
        text = (msg.get("text") or {}).get("body", "")

        # Resposta simples (teste)
        if from_number:
            body = f"✅ Recebi sua mensagem: {text}"
            send_text(from_number, body)
    except Exception:
        pass
    return {"ok": True}
