import sys
import json
import httpx

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/chat"
    payload = {"messages": [{"role": "user", "content": "give 2 short testing strategies"}]}
    with httpx.Client(timeout=120) as client:
        r = client.post(url, json=payload)
        status = r.status_code
        text = r.text
        try:
            data = r.json()
        except Exception:
            data = None
    # Always print status and body
    print(f"STATUS: {status}")
    print("BODY:")
    print(text)
    # If success and assistant content present, print it clearly
    if status == 200 and isinstance(data, dict) and "content" in data:
        print("\nASSISTANT CONTENT:\n" + str(data["content"]))

if __name__ == "__main__":
    main()
