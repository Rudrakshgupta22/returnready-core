import pytest
import time
from unittest.mock import patch
from policy_engine import evaluate_return_or_warranty, mint_token, verify_token

@pytest.fixture(autouse=True)
def test_secret(monkeypatch):
    monkeypatch.setenv("RETURNREADY_SECRET", "returnready-test-secret")

# Mock the data.json load to test specific boundaries without touching the real file
@pytest.fixture
def mock_data():
    return {
        "policies": {"standard_return_days": 30, "defect_warranty_days": 365},
        "products": [{"id": "prod_1", "name": "Test Item", "category": "Audio"}],
        "orders": [
            {"order_id": "ORD-29", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 29, "price_paid": 100},
            {"order_id": "ORD-30", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 30, "price_paid": 100},
            {"order_id": "ORD-31", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 31, "price_paid": 100},
            {"order_id": "ORD-364", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 364, "price_paid": 100},
            {"order_id": "ORD-365", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 365, "price_paid": 100},
            {"order_id": "ORD-366", "product_id": "prod_1", "product_name": "Test Item", "days_since_purchase": 366, "price_paid": 100}
        ]
    }

@patch('policy_engine.load_data')
def test_return_boundaries(mock_load_data, mock_data):
    mock_load_data.return_value = mock_data
    
    # Day 29 and 30 should be RETURN_ELIGIBLE
    res_29 = evaluate_return_or_warranty("ORD-29")
    assert res_29["status"] == "RETURN_ELIGIBLE"
    
    res_30 = evaluate_return_or_warranty("ORD-30")
    assert res_30["status"] == "RETURN_ELIGIBLE"

    # Day 31 should fall to TRIAGE_REQUIRED if defective
    res_31 = evaluate_return_or_warranty("ORD-31", issue_type="defective")
    assert res_31["status"] == "TRIAGE_REQUIRED"

@patch('policy_engine.load_data')
def test_warranty_boundaries(mock_load_data, mock_data):
    mock_load_data.return_value = mock_data
    
    # Day 364 and 365 should be TRIAGE_REQUIRED
    res_364 = evaluate_return_or_warranty("ORD-364", issue_type="defective")
    assert res_364["status"] == "TRIAGE_REQUIRED"
    
    res_365 = evaluate_return_or_warranty("ORD-365", issue_type="defective")
    assert res_365["status"] == "TRIAGE_REQUIRED"

    # Day 366 should be INELIGIBLE
    res_366 = evaluate_return_or_warranty("ORD-366", issue_type="defective")
    assert res_366["status"] == "INELIGIBLE"

@patch('policy_engine.load_data')
def test_resolved_outcome(mock_load_data, mock_data):
    mock_load_data.return_value = mock_data
    
    # If the user fixed the item, they shouldn't get a claim token
    res = evaluate_return_or_warranty("ORD-31", issue_type="defective", troubleshooting_outcome="resolved")
    assert res["status"] == "RESOLVED_NO_CLAIM"
    assert "verification_token" not in res

def test_token_tampering():
    """Verify that changing a token invalidates the HMAC signature."""
    order_id = "ORD-TEST"
    valid_token = mint_token(order_id)
    
    # Valid check
    assert verify_token(order_id, valid_token) is True
    
    # Tamper with the signature
    parts = valid_token.split("-")
    tampered_sig = "A" + parts[2][1:]
    tampered_token = f"{parts[0]}-{parts[1]}-{tampered_sig}"
    
    assert verify_token(order_id, tampered_token) is False
    
    # Wrong Order ID
    assert verify_token("ORD-HACKER", valid_token) is False

def test_expired_token():
    order_id = "ORD-EXPIRED"
    with patch("policy_engine.time.time", return_value=1000):
        expired_token = mint_token(order_id, ttl=1)

    with patch("policy_engine.time.time", return_value=1002):
        assert verify_token(order_id, expired_token) is False

@patch('policy_engine.load_data')
def test_unknown_order(mock_load_data, mock_data):
    mock_load_data.return_value = mock_data

    result = evaluate_return_or_warranty("can i return my sony tv")

    assert result["found"] is False
    assert result["status"] == "ORDER_NOT_FOUND"

def test_missing_returnready_secret(monkeypatch):
    monkeypatch.delenv("RETURNREADY_SECRET")

    with pytest.raises(RuntimeError, match="RETURNREADY_SECRET must be set"):
        mint_token("ORD-TEST")

    with pytest.raises(RuntimeError, match="RETURNREADY_SECRET must be set"):
        verify_token("ORD-TEST", "DIAG-1000-" + "A" * 64)