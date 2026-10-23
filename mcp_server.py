import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from policy_engine import find_product, evaluate_return_or_warranty, verify_token

mcp = FastMCP(
    "ReturnReady-MCP",
    dependencies=["pydantic"],
    host="127.0.0.1",
    port=8001
)

MOBILE_STATE_PATH = Path(__file__).parent / "mobile_state.json"

@mcp.tool()
def get_product_info(product_query: str, intended_use: str = "") -> str:
    product = find_product(product_query)
    if not product:
        return json.dumps({
            "found": False, 
            "message": f"Product '{product_query}' not found in catalog. Try asking about the 'SoundPulse Pro' or 'AeroBuds Mini'."
        })

    risk_info = None
    if intended_use:
        use_key = intended_use.lower().replace(" ", "_")
        for key, value in product.get("return_risk_by_use_case", {}).items():
            if key in use_key or use_key in key:
                risk_info = value
                break

    return json.dumps({
        "found": True,
        "product": product,
        "matched_return_risk": risk_info or {"risk": "MODERATE", "reason": "Standard return rate."}
    })

@mcp.tool()
def check_return_or_warranty(
    order_or_product_query: str,
    issue_type: str = "defective",
    troubleshooting_outcome: str = "not_attempted"
) -> str:
    result = evaluate_return_or_warranty(
        order_or_product_query=order_or_product_query,
        issue_type=issue_type,
        troubleshooting_outcome=troubleshooting_outcome
    )
    return json.dumps(result)

@mcp.tool()
def verify_claim_token(order_id: str, token: str) -> str:
    is_valid = verify_token(order_id, token)
    return json.dumps({
        "valid": is_valid, 
        "status": "APPROVED" if is_valid else "FRAUD_DETECTED",
        "message": "Token verification passed." if is_valid else "Invalid or expired token signature."
    })

@mcp.tool()
def send_to_mobile(card_type: str, title: str, payload_json: str) -> str:
    try:
        data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    except Exception:
        data = {"raw": str(payload_json)}

    state = {
        "card_type": card_type,
        "title": title,
        "data": data
    }
    with open(MOBILE_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    return json.dumps({"status": "SUCCESS", "message": f"Pushed {card_type} card to mobile."})

if __name__ == "__main__":
    # Fully enforces Streamable HTTP for the Hackathon requirements
    mcp.run(transport="streamable-http")