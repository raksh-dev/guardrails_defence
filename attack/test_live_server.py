import sys
import json
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Please install httpx first: pip install httpx")
    sys.exit(1)

# Default live server URL
BASE_URL = "http://localhost:8000"

DATA_DIR = Path(__file__).resolve().parent / "data"

def load_data(filename: str):
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))

def test_endpoint(client: httpx.Client, endpoint: str, cases: list, payload_builder):
    print(f"\n{'='*80}\nTesting Live Endpoint : {endpoint}\n{'='*80}")
    
    blocked = 0
    slipped = 0
    
    for case in cases:
        payload = payload_builder(case)
        try:
            response = client.post(endpoint, json=payload, timeout=10.0)
            status = response.status_code
            
            # The guardrail system returns 400 when an attack is blocked
            if status == 400:
                print(f"[BLOCKED] {case['id']:<15} {case.get('description', '')[:50]:<50} (status {status})")
                blocked += 1
            else:
                print(f"[GAP    ] {case['id']:<15} {case.get('description', '')[:50]:<50} (status {status})")
                slipped += 1
                
        except httpx.RequestError as e:
            print(f"[ERROR  ] Failed to connect for {case['id']}. Is the server running? ({e})")
            return

    print("-" * 80)
    print(f"Total attacks fired : {len(cases)}")
    print(f"  BLOCKED           : {blocked}")
    print(f"  SLIPPED (GAPS)    : {slipped}")

def run_live_tests():
    print(f"Starting live adversarial tests against {BASE_URL}")
    print("Make sure your application is running (e.g. `uvicorn defence.main:app --reload`)")
    
    try:
        adv_cases = load_data("adversarial_prompts.json")
        pdf_cases = load_data("pdf_adversarial_prompts.json")
    except Exception as e:
        print(f"Error loading test data: {e}")
        return

    # Filter out benign baseline cases from raw attack counts
    chat_attacks = [c for c in adv_cases if not c["id"].startswith("BENIGN")]
    pdf_attacks = [c for c in pdf_cases if not c["id"].startswith("BENIGN")]

    with httpx.Client(base_url=BASE_URL) as client:
        # 1. Test /chat/ endpoint
        test_endpoint(
            client, 
            "/chat/", 
            chat_attacks, 
            lambda case: {"query": case["user_prompt"]}
        )
        
        # 2. Test /rag/query endpoint
        test_endpoint(
            client, 
            "/rag/query", 
            pdf_attacks, 
            lambda case: {"query": case["user_prompt"], "book_id": 1}
        )
        
        # 3. Test /conversations/{id}/messages endpoint
        # We assume conversation ID 1 exists or can be accessed
        test_endpoint(
            client, 
            "/conversations/1/messages", 
            chat_attacks, 
            lambda case: {"role": "user", "content": case["user_prompt"]}
        )

if __name__ == "__main__":
    run_live_tests()
