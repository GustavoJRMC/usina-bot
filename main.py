# main.py
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, Tuple

import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI()

# ====== Config ======
VERIFY_TOKEN   = os.getenv("WHATSAPP_VERIFY_TOKEN", "verifyJR2025")
WABA_PHONE_ID  = os.getenv("WABA_PHONE_ID")           # ex.: 778846328642993
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")          # token do painel da Meta

# ====== Estado em memória (para demo) ======
# Em produção, troque por Redis/DB.
SESSOES: Dict[str, Dict[str, Any]] = {}

# Ordem e rótulos das perguntas (Modo A – perguntas guiadas)
CAMPOS = [
    ("obra",            "Qual é o número/nome da Obra?"),
    ("data",            "Data (dd/mm/aaaa)?"),
    ("turno",           "Turno (Diurno / Noturno)?"),
    ("horario",         "Horário das atividades (ex.: 07:00 às 17:00)?"),
    ("previsto",        "Previsto (quantidade, apenas número – ex.: 150)?"),
    ("cbuq",            "CBUQ (toneladas – ex.: 11,5 ton)?"),
    ("equipe",          "Equipe (ex.: Drenagem 01)?"),
    ("encarregado",     "Encarregado (nome – empresa)?"),
    ("local",           "Local (ex.: BR-101)?"),
    ("pista",           "Pista (ex.: 1 / 2 / 3)?"),
    ("sentido",         "Sentido (ex.: Norte / Sul / Leste / Oeste)?"),
    ("trechos",         "Trechos (ex.: Km 38+000 ao Km 37+000)?"),
    ("cidade",          "Cidade (ex.: Três Forquilhas - RS)?"),
    ("dmt",             "DMT (km – apenas número, ex.: 130)?"),
]

# ====== Utilitários ======
def send_text(to: str, body: str) -> None:
    """Envia uma mensagem de texto via WhatsApp Cloud API."""
    if not (WABA_PHONE_ID and WHATSAPP_TOKEN):
        print("⚠️  Envio desabilitado: faltam variáveis de ambiente WABA_PHONE_ID/WHATSAPP_TOKEN.")
        return

    url = f"https://graph.facebook.com/v20.0/{WABA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        print("↩️ Resposta enviada:", r.status_code, r.text)
    except Exception as e:
        print("Erro ao enviar:", e)

def normaliza_decimal(txt: str) -> str:
    """Aceita 11,5 ou 11.5 e devolve string padronizada com vírgula."""
    t = txt.strip()
    t = t.replace(" ", "")
    t = t.replace("ton", "").replace("tons", "").replace("t", "")
    t = t.replace(",", ".")
    # manter no formato com vírgula para exibir
    try:
        val = float(t)
        # exibe com vírgula no Brasil
        return f"{val}".replace(".", ",")
    except:
        return txt

def valida_resposta(campo: str, valor: str) -> Tuple[bool, str]:
    """Validações básicas por campo. Retorna (ok, valor_normalizado)."""
    v = valor.strip()

    if campo == "data":
        # formato dd/mm/aaaa
        try:
            dt = datetime.strptime(v, "%d/%m/%Y")
            return True, dt.strftime("%d/%m/%Y")
        except:
            return False, "Formato de data inválido. Use dd/mm/aaaa (ex.: 01/09/2025)."

    if campo in ("previsto", "pista", "dmt"):
        # aceitar apenas números inteiros
        digits = re.sub(r"[^\d]", "", v)
        if digits == "":
            return False, "Digite apenas números (ex.: 150)."
        return True, digits

    if campo == "cbuq":
        # aceitar 11,5 / 11.5 e guardar com vírgula
        normalized = normaliza_decimal(v)
        # validar que é número
        try:
            float(normalized.replace(",", "."))
            return True, f"{normalized} ton"
        except:
            return False, "Informe um número (ex.: 11,5 ton)."

    # Demais campos: apenas limpar espaços
    return True, v

def resumo_dados(dados: Dict[str, str]) -> str:
    """Monta o resumo no padrão que você indicou."""
    def get(k, default=""):
        return dados.get(k, default)

    linhas = [
        "Programação",
        f"Data: {get('data')}",
        f"Obra: {get('obra')}",
        f"Turno: {get('turno')}",
        "Horário das atividades:",
        f"{get('horario')}",
        f"Previsto: {get('previsto')}",
        f"CBUQ: {get('cbuq')}",
        f"Equipe: {get('equipe')}",
        f"Encarregado: {get('encarregado')}",
        f"Local: {get('local')}",
        f"Pista: {get('pista')}",
        f"Sentido: {get('sentido')}",
        f"Trechos: {get('trechos')}",
        f"Cidade: {get('cidade')}",
        f"DMT: {get('dmt')} km",
    ]
    return "\n".join(linhas)

def ajuda_texto() -> str:
    return (
        "🤖 *Bot Usina – Perguntas guiadas*\n"
        "- Envie *iniciar* para começar.\n"
        "- Envie *resumo* para ver o que já foi preenchido.\n"
        "- Envie *reiniciar* para começar do zero.\n"
        "- Envie *cancelar* para encerrar a sessão atual.\n"
        "No final, envio um resumo no formato da sua programação."
    )

# ====== Webhook: verificação ======
@app.get("/webhook")
def verify(mode: str = "", challenge: str = "", token: str = ""):
    """Verificação do webhook pelo Meta (GET)."""
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge, status_code=200)
    return PlainTextResponse("forbidden", status_code=403)

# ====== Webhook: recebimento ======
@app.post("/webhook")
async def incoming(req: Request):
    data = await req.json()
    print("🔔 Mensagem recebida:", data)

    # Ignorar callbacks que não são de mensagem
    try:
        entry = data["entry"][0]["changes"][0]["value"]
    except Exception:
        return JSONResponse({"ok": True})

    # Mensagens normais
    msgs = entry.get("messages", [])
    if not msgs:
        return JSONResponse({"ok": True})

    msg = msgs[0]
    from_number = msg.get("from")
    msg_type = msg.get("type")
    text_body = ""
    if msg_type == "text":
        text_body = (msg.get("text") or {}).get("body", "") or ""
    else:
        text_body = f"[{msg_type}]"

    # Comandos globais
    low = text_body.strip().lower()
    if low in ("ajuda", "help", "/help"):
        send_text(from_number, ajuda_texto())
        return JSONResponse({"ok": True})

    if low in ("cancelar", "parar"):
        SESSOES.pop(from_number, None)
        send_text(from_number, "Sessão cancelada. Envie *iniciar* quando quiser retomar.")
        return JSONResponse({"ok": True})

    if low in ("reiniciar", "reset", "começar"):
        SESSOES.pop(from_number, None)
        low = "iniciar"  # cai no fluxo de início

    if low in ("resumo", "/resumo"):
        sess = SESSOES.get(from_number)
        if not sess or not sess.get("dados"):
            send_text(from_number, "Ainda não há dados. Envie *iniciar* para começar.")
        else:
            send_text(from_number, "📄 *Resumo parcial:*\n" + resumo_dados(sess["dados"]))
        return JSONResponse({"ok": True})

    # Fluxo guiado
    if low in ("iniciar", "start"):
        # cria sessão
        SESSOES[from_number] = {"i": 0, "dados": {}}
        send_text(from_number, "Vamos começar! " + CAMPOS[0][1] + "\n\n(Envie *cancelar* a qualquer momento.)")
        return JSONResponse({"ok": True})

    # Se já existe sessão, continuar
    sess = SESSOES.get(from_number)
    if not sess:
        # Sem sessão: orientar usuário
        send_text(from_number, "Olá! Envie *iniciar* para começar o preenchimento. Envie *ajuda* para ver os comandos.")
        return JSONResponse({"ok": True})

    i = sess["i"]
    dados = sess["dados"]

    # Valida resposta para o campo atual
    if i < len(CAMPOS):
        campo, pergunta = CAMPOS[i]
        ok, valor_norm = valida_resposta(campo, text_body)
        if not ok:
            send_text(from_number, f"⚠️ {valor_norm}\n\n{pergunta}")
            return JSONResponse({"ok": True})

        # Salva e avança
        dados[campo] = valor_norm
        sess["i"] = i + 1

    # Verifica se terminou
    if sess["i"] >= len(CAMPOS):
        # Finaliza
        texto = "✅ *Coleta concluída!*\n\n" + resumo_dados(dados)
        send_text(from_number, texto)
        send_text(from_number, "Se quiser refazer, envie *reiniciar*. Em breve salvaremos automaticamente na planilha. 😉")
        # (ETAPA FUTURA) -> salvar no Google Sheets aqui
        SESSOES.pop(from_number, None)
        return JSONResponse({"ok": True})

    # Próxima pergunta
    prox_campo, prox_pergunta = CAMPOS[sess["i"]]
    send_text(from_number, prox_pergunta)
    return JSONResponse({"ok": True})
