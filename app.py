import json
import os
import re
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Official Streamable HTTP client import required by audit
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

app = FastAPI(title="ReturnReady Alexa+ Simulator")

BASE_DIR = Path(__file__).parent
MOBILE_STATE_PATH = BASE_DIR / "mobile_state.json"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp") 

class ChatRequest(BaseModel):
    message: str

class VisionDefectRequest(BaseModel):
    order_id: str = "ORD-902"
    simulated_image_issue: str = "Cracked charging contact pin & dark LED on left AeroBuds Mini earbud"

class ShipReplacementRequest(BaseModel):
    order_id: str
    token: str

def parse_mcp_result(mcp_res) -> dict:
    if not getattr(mcp_res, "content", None):
        return {}
    raw_text = mcp_res.content[0].text
    try:
        return json.loads(raw_text)
    except Exception as e:
        print(f"[MCP Tool Raw Output]: {raw_text} | Error: {e}")
        return {"error": raw_text}

async def run_smart_mcp_router(user_message: str, session: ClientSession):
    msg = user_message.lower()
    called_tools = []

    if any(phrase in msg for phrase in ["risk", "should i buy", "good for", "gym"]):
        product_query = "BrewMaster" if any(w in msg for w in ["espresso", "coffee"]) else "SoundPulse"
        intended_use = "gym_and_running" if any(w in msg for w in ["gym", "run", "workout", "sweat"]) else "flights_and_travel"

        called_tools.append("get_product_info")
        mcp_res = await session.call_tool("get_product_info", arguments={"product_query": product_query, "intended_use": intended_use})
        prod_data = parse_mcp_result(mcp_res)
        
        if prod_data.get("found") is False:
            return prod_data.get("message", "Product not found."), [prod_data]

        called_tools.append("send_to_mobile")
        await session.call_tool("send_to_mobile", arguments={
            "card_type": "product_comparison",
            "title": f"{prod_data['product']['name']} — Return-Risk Analysis",
            "payload_json": json.dumps(prod_data),
        })

        product = prod_data["product"]
        risk = prod_data["matched_return_risk"]
        if "HIGH" in risk["risk"]:
            reply = f"The {product['name']} is ${product['price']}, but it has a HIGH return risk for gym workouts because the earcups aren't sweatproof. I've sent the full specs to your phone."
        else:
            reply = f"The {product['name']} has a LOW return risk for your needs. I've sent the spec sheet to your phone."
        
        return reply, called_tools

    elif re.search(r"\b(red|dark|blink|didn't work|dead|still broken)\b", msg):
        # Prevent hijacking: check if they are talking about a specific product, otherwise use the whole message
        known_products = {"aerobuds": "AeroBuds", "earbud": "AeroBuds", "charging": "AeroBuds", "soundpulse": "SoundPulse", "brewmaster": "BrewMaster"}
        target = next((product for keyword, product in known_products.items() if keyword in msg), msg)

        called_tools.append("check_return_or_warranty")
        mcp_res = await session.call_tool("check_return_or_warranty", arguments={
            "order_or_product_query": target, "issue_type": "defective", "troubleshooting_outcome": "failed_confirmed_defect"
        })
        
        warranty_data = parse_mcp_result(mcp_res)
        
        if warranty_data.get("found") is False:
            return warranty_data.get("message", "Order not found."), [warranty_data]

        called_tools.append("send_to_mobile")
        await session.call_tool("send_to_mobile", arguments={
            "card_type": "warranty_verified", "title": warranty_data.get("headline", "Warranty Approved"), "payload_json": json.dumps(warranty_data)
        })
        
        token = warranty_data.get("verification_token", "DIAG-VERIFIED")
        reply = f"That confirms a hardware fault. I've generated Pre-Verified Diagnostic Token {token} so you skip support queues, and sent your instant replacement pass to your phone."
        return reply, called_tools

    elif any(word in msg for word in ["return", "warranty", "stopped", "broken", "refund", "aerobuds", "ord-"]):
        known_products = {"aerobuds": "AeroBuds", "earbud": "AeroBuds", "charging": "AeroBuds", "soundpulse": "SoundPulse", "brewmaster": "BrewMaster"}
        target = next((product for keyword, product in known_products.items() if keyword in msg), msg)
        issue = "defective" if any(w in msg for w in ["stopped", "broken", "defect", "charging"]) else "changed_mind"

        called_tools.append("check_return_or_warranty")
        mcp_res = await session.call_tool("check_return_or_warranty", arguments={
            "order_or_product_query": target, "issue_type": issue, "troubleshooting_outcome": "not_attempted"
        })
        triage_data = parse_mcp_result(mcp_res)
        
        if triage_data.get("found") is False:
            return triage_data.get("message", "Item not found."), [triage_data]

        called_tools.append("send_to_mobile")
        await session.call_tool("send_to_mobile", arguments={
            "card_type": "triage_or_return", "title": triage_data.get("headline", "Return & Warranty Status"), "payload_json": json.dumps(triage_data)
        })

        if triage_data.get("status") == "TRIAGE_REQUIRED":
            reply = f"Your {triage_data['product_name']} is past the refund window, but covered by the defect warranty. Let's run a 5-second check: hold the back case button for 5 seconds—does the left LED blink amber or stay dark?"
        elif triage_data.get("status") == "RETURN_ELIGIBLE":
            reply = f"Good news! Your {triage_data['product_name']} is within the return window. I've sent a one-tap prepaid return QR code to your phone."
        else:
            reply = f"I've checked the status for your {triage_data['product_name']}. The details are on your screen."
            
        return reply, called_tools

    else:
        return "I can help check return risks, warranties, or specific product specs. For this demo, try asking about the SoundPulse Pro or AeroBuds Mini.", []

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    async with streamablehttp_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            protocol_version = str(init_result.protocolVersion)
            if protocol_version != "2025-11-25":
                raise RuntimeError(f"Unsupported MCP protocol version: {protocol_version}. Expected 2025-11-25.")
            
            reply, called_tools = await run_smart_mcp_router(req.message, session)
            return {
                "reply": reply,
                "mcp_protocol_version": protocol_version,
                "transport": "streamable-http",  # Now accurately reported for telemetry
                "active_skill": "returnready (SKILL.md)",
                "aws_engine": "Simulated Multimodal / Local Agent",
                "tools_called": called_tools
            }

@app.post("/api/vision-verify")
async def vision_verify_endpoint(req: VisionDefectRequest):
    from policy_engine import mint_token
    token = mint_token(req.order_id) 
    
    vision_payload = {
        "found": True,
        "order_id": req.order_id,
        "product_name": "AeroBuds Mini",
        "status": "WARRANTY_APPROVED_VERIFIED",
        "verification_token": token,
        "headline": f"Simulated Vision Defect Verified",
        "reason": f"Simulated AI Vision Analysis confirmed hardware issue: '{req.simulated_image_issue}'.",
        "next_step": "Instant replacement unlocked. Tap below to ship your free replacement unit.",
    }

    async with streamablehttp_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            protocol_version = str(init_result.protocolVersion)
            if protocol_version != "2025-11-25":
                raise RuntimeError(f"Unsupported MCP protocol version: {protocol_version}. Expected 2025-11-25.")
            await session.call_tool("send_to_mobile", arguments={
                "card_type": "warranty_verified",
                "title": vision_payload["headline"],
                "payload_json": json.dumps(vision_payload)
            })

    return {
        "reply": f"I simulated analyzing your photo and confirmed the damaged charging contact on your AeroBuds Mini. Your Pre-Verified Claim Token {token} is now on your phone.",
        "tools_called": ["simulated_bedrock_converse", "send_to_mobile"],
        "verification_token": token,
    }

@app.post("/api/ship-replacement")
async def ship_replacement(req: ShipReplacementRequest):
    async with streamablehttp_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            protocol_version = str(init_result.protocolVersion)
            if protocol_version != "2025-11-25":
                raise RuntimeError(f"Unsupported MCP protocol version: {protocol_version}. Expected 2025-11-25.")
            mcp_res = await session.call_tool("verify_claim_token", arguments={"order_id": req.order_id, "token": req.token})
            result = parse_mcp_result(mcp_res)
            
            title = "Replacement Shipped!" if result.get("valid") else "Verification Failed"
            
            await session.call_tool("send_to_mobile", arguments={
                "card_type": "warranty_verified",
                "title": title,
                "payload_json": json.dumps({"reason": result.get("message"), "verification_token": req.token})
            })
    return {"status": result.get("status"), "message": result.get("message")}

@app.get("/api/mobile-state")
async def get_mobile_state():
    if MOBILE_STATE_PATH.exists():
        return json.loads(MOBILE_STATE_PATH.read_text(encoding="utf-8"))
    return {
        "card_type": "empty",
        "title": "ReturnReady Mobile Companion",
        "data": {"message": "Ask Alexa+ about a product or return to see live cards here."},
    }

@app.get("/")
async def serve_ui():
    return FileResponse(BASE_DIR / "index.html")