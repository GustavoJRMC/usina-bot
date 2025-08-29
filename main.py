from fastapi import FastAPI, Request
import os

app = FastAPI()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "verifyJR2025")

@app.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    return {"status": "forbidden"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("🔔 Mensagem recebida:", data)

    # Responde só para confirmar recebimento (200 OK)
    return {"status": "received"}
