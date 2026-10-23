import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import hmac
import time

DATA_PATH = Path(__file__).parent / "data.json"

def _secret_key() -> bytes:
    """Lazily load the secret key to prevent forgeable tokens."""
    secret = os.getenv("RETURNREADY_SECRET")
    if not secret:
        raise RuntimeError("RETURNREADY_SECRET must be set in the environment.")
    return secret.encode("utf-8")

def load_data() -> dict:
    """Loads the synthetic catalog, orders, and policy rules."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def find_product(query: str) -> dict | None:
    """Finds a product by ID, partial name, or category."""
    data = load_data()
    q = query.lower().strip()
    if len(q) < 3:
        return None
        
    for product in data["products"]:
        if q in product["id"].lower() or q in product["name"].lower() or q in product["category"].lower():
            return product
    return None

def mint_token(order_id: str, ttl: int = 900) -> str:
    """Generates a verifiable HMAC-SHA256 token with an expiration timestamp."""
    exp = int(time.time()) + ttl
    sig = hmac.new(_secret_key(), f"{order_id}:{exp}".encode(), hashlib.sha256).hexdigest().upper()
    return f"DIAG-{exp}-{sig}"

def verify_token(order_id: str, token: str) -> bool:
    """Verifies the full 64-character HMAC signature and checks expiration."""
    try:
        prefix, exp, sig = token.split("-")
        if prefix != "DIAG" or len(sig) != 64: 
            return False
        
        expected_sig = hmac.new(_secret_key(), f"{order_id}:{exp}".encode(), hashlib.sha256).hexdigest().upper()
        return hmac.compare_digest(sig, expected_sig) and int(exp) > time.time()
    except ValueError:
        return False

def evaluate_return_or_warranty(
    order_or_product_query: str,
    issue_type: str = "defective",
    troubleshooting_outcome: str = "not_attempted"
) -> dict:
    data = load_data()
    return_window = data["policies"]["standard_return_days"]
    warranty_window = data["policies"]["defect_warranty_days"]

    q = order_or_product_query.lower().strip()
    if len(q) < 3:
        return {"found": False, "status": "INVALID_QUERY", "message": "Query too short."}
    
    matched_order = None
    for o in data["orders"]:
        # Prefer exact match for Order ID if the user provided one
        if q == o["order_id"].lower():
            matched_order = o
            break
        # Fallback to product name matching if it's clearly not a partial Order ID
        elif not q.startswith("ord-") and q in o["product_name"].lower():
            matched_order = o
            break

    if not matched_order:
        return {
            "found": False, 
            "status": "ORDER_NOT_FOUND", 
            "message": f"I don't see '{order_or_product_query}' in your recent order history. For this demo, try asking about the 'AeroBuds' or 'SoundPulse' headphones."
        }

    product = find_product(matched_order["product_id"]) or {}
    days_elapsed = matched_order["days_since_purchase"]
    purchase_date_str = (datetime.now() - timedelta(days=days_elapsed)).strftime("%Y-%m-%d")
    is_defect = any(word in issue_type.lower() for word in ["defect", "broken", "damaged", "hardware", "fault"])

    if days_elapsed <= return_window:
        return {
            "found": True,
            "order_id": matched_order["order_id"],
            "product_name": matched_order["product_name"],
            "days_since_purchase": days_elapsed,
            "status": "RETURN_ELIGIBLE",
            "headline": f"Eligible for Instant Refund ({return_window - days_elapsed} Days Left)",
            "reason": f"Purchased {days_elapsed} days ago ({purchase_date_str}), inside the {return_window}-day return window.",
            "next_step": "One-tap prepaid QR drop-off code sent to mobile."
        }

    if days_elapsed <= warranty_window and is_defect:
        
        if troubleshooting_outcome == "resolved":
            return {
                "found": True,
                "order_id": matched_order["order_id"],
                "product_name": matched_order["product_name"],
                "status": "RESOLVED_NO_CLAIM",
                "headline": "Device Reset Successful",
                "reason": "Hardware is functioning normally after diagnostic reset.",
                "next_step": "No further action needed."
            }
            
        if troubleshooting_outcome != "failed_confirmed_defect":
            troubleshooting_outcome = "not_attempted"
            
        if troubleshooting_outcome == "not_attempted":
            return {
                "found": True,
                "order_id": matched_order["order_id"],
                "product_name": matched_order["product_name"],
                "days_since_purchase": days_elapsed,
                "status": "TRIAGE_REQUIRED",
                "headline": "Warranty Covered — 10-Second Voice Check Required",
                "diagnostic_instruction": product.get("diagnostic_step", "Power cycle the device for 5 seconds."),
                "reason": (
                    f"Order is {days_elapsed} days old (past the {return_window}-day refund window, "
                    f"but covered by the {warranty_window}-day defect warranty)."
                ),
                "next_step": "Ask the user to try the diagnostic_instruction and report what happens."
            }

        token = mint_token(matched_order['order_id'])
        
        return {
            "found": True,
            "order_id": matched_order["order_id"],
            "product_name": matched_order["product_name"],
            "days_since_purchase": days_elapsed,
            "status": "WARRANTY_APPROVED_VERIFIED",
            "verification_token": token,
            "headline": f"Warranty Replacement Approved (Token: {token})",
            "reason": "Hardware fault reported and unresolved after guided diagnostic. Customer support queue bypassed.",
            "next_step": "Tap 'Ship Free Replacement' on your Mobile Companion card."
        }

    return {
        "found": True,
        "order_id": matched_order["order_id"],
        "product_name": matched_order["product_name"],
        "status": "INELIGIBLE",
        "headline": "Outside Return & Warranty Coverage",
        "reason": f"Purchased {days_elapsed} days ago and does not meet warranty criteria.",
        "next_step": "View paid repair options."
    }