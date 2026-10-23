import logging

logger = logging.getLogger(__name__)
import json
import sys

# Try to import requests; if missing, we catch it later
try:
    import requests
except ImportError:
    requests = None

def submit_transaction(hex_transaction: str):
    """
    Submits a transaction to the Kaspa Network via the Public Relay.
    This bypasses the local node entirely.
    """
    # 1. Check for library
    if not requests:
        logger.info("CRITICAL ERROR: 'requests' library is not installed.", file=sys.stderr)
        return {"error": "Server Configuration Error: Missing 'requests' library"}

    # 2. Define Public Relay URL
    url = "https://api.kaspa.org/transactions"
    payload = {"transactionHex": hex_transaction}
    
    logger.info(f"--- [NEW CODE ACTIVE] BROADCASTING TO {url} ---", file=sys.stderr, flush=True)

    try:
        # 3. Send Request (10s timeout)
        response = requests.post(url, json=payload, timeout=10)
        
        logger.info(f"--- RELAY STATUS: {response.status_code} ---", file=sys.stderr, flush=True)
        
        if response.status_code == 200:
            # Success
            tx_id = response.json().get("transactionId")
            return {"result": tx_id}
        else:
            # Relay Rejected It
            logger.info(f"RELAY ERROR BODY: {response.text}", file=sys.stderr, flush=True)
            return {"error": f"Relay Rejected: {response.text}"}

    except Exception as e:
        logger.info(f"CONNECTION EXCEPTION: {str(e)}", file=sys.stderr, flush=True)
        return {"error": f"Connection Failed: {str(e)}"}
