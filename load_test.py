import requests
import time
import concurrent.futures
from pathlib import Path

# Server endpoints
SERVERS = [
    "http://localhost:8000",
    "http://localhost:8001", 
    "http://localhost:8002"
]

# PDF files to upload
PDF_FILES = [
    r"C:\Users\shiva\Downloads\Unit-4 (1).pdf",
    r"C:\Users\shiva\Downloads\Unit-1.pdf",
    r"C:\Users\shiva\Downloads\DM - 2.pdf"
]

def create_user_and_login(server_url, email, password, name):
    """Create a user and login to get auth token"""
    try:
        # Signup
        signup_url = f"{server_url}/api/v1/signup"
        signup_data = {"name": name, "email": email, "password": password}
        
        try:
            response = requests.post(signup_url, json=signup_data)
            print(f"Server {server_url}: Signup status {response.status_code}")
        except:
            pass  # User might already exist
        
        # Login
        login_url = f"{server_url}/api/v1/login"
        login_data = {"email": email, "password": password}
        response = requests.post(login_url, json=login_data)
        
        if response.status_code == 200:
            # Token is in the cookie, not the response body
            token = response.cookies.get("access_token")
            print(f"Server {server_url}: Login successful for {email}, token: {token[:20] if token else 'None'}...")
            return token
        else:
            print(f"Server {server_url}: Login failed for {email} - {response.text}")
            return None
    except Exception as e:
        print(f"Server {server_url}: Auth error - {e}")
        return None

def upload_pdf(server_url, pdf_path, auth_token):
    """Upload a PDF to the server"""
    try:
        upload_url = f"{server_url}/api/v1/rag/newChat"
        cookies = {"access_token": auth_token}
        
        pdf_file = Path(pdf_path)
        print(f"Server {server_url}: Checking PDF file - {pdf_path}")
        if not pdf_file.exists():
            print(f"Server {server_url}: PDF file not found - {pdf_path}")
            return None
        
        print(f"Server {server_url}: PDF file exists, size: {pdf_file.stat().st_size} bytes")
        
        with open(pdf_path, 'rb') as f:
            files = {"file": (pdf_file.name, f, 'application/pdf')}
            print(f"Server {server_url}: Starting upload of {pdf_file.name}")
            response = requests.post(upload_url, cookies=cookies, files=files)
            print(f"Server {server_url}: Upload response status: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            doc_id = result.get("document_id")
            status = result.get("status")
            already_seen = result.get("already_seen")
            print(f"Server {server_url}: Uploaded {pdf_file.name} - Doc ID: {doc_id}, Status: {status}, Already seen: {already_seen}")
            return doc_id
        else:
            print(f"Server {server_url}: Upload failed for {pdf_file.name} - Status: {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        print(f"Server {server_url}: Upload error for {pdf_path} - {e}")
        import traceback
        traceback.print_exc()
        return None

def check_document_status(server_url, doc_id, auth_token):
    """Check the status of document processing"""
    try:
        status_url = f"{server_url}/api/v1/rag/documents/{doc_id}"
        cookies = {"access_token": auth_token}
        response = requests.get(status_url, cookies=cookies)
        
        if response.status_code == 200:
            result = response.json()
            print(f"Server {server_url}: Doc {doc_id} status check response: {result}")
            return result
        else:
            print(f"Server {server_url}: Status check failed with status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"Server {server_url}: Status check error - {e}")
        return None

def monitor_document_processing(server_url, doc_id, auth_token, max_wait=300):
    """Monitor document processing until completion or timeout"""
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status_data = check_document_status(server_url, doc_id, auth_token)
        if status_data:
            status = status_data.get("status")
            print(f"Server {server_url}: Doc {doc_id} status - {status}")
            
            if status in ["ready", "failed"]:
                return status_data
        
        time.sleep(5)
    
    return {"status": "timeout"}

def run_load_test():
    """Run load test across all servers"""
    print("Starting load test across 3 servers...")
    print("=" * 50)
    
    # Use existing user for all servers instead of creating new ones
    email = "loadtest_user_0@test.com"
    password = "testpass123"
    name = "Load Test User 0"
    
    auth_tokens = []
    for i, server_url in enumerate(SERVERS):
        token = create_user_and_login(server_url, email, password, name)
        auth_tokens.append(token)
        print(f"Server {server_url}: Token stored: {token[:20] if token else 'None'}...")
    
    print("\n" + "=" * 50)
    print("Starting PDF uploads...")
    print("=" * 50)
    
    # Upload PDFs to each server (1 PDF per server)
    doc_ids = []
    
    for i, (server_url, pdf_path, token) in enumerate(zip(SERVERS, PDF_FILES, auth_tokens)):
        if token:
            print(f"\nProcessing upload to {server_url} with {pdf_path}")
            doc_id = upload_pdf(server_url, pdf_path, token)
            doc_ids.append((server_url, doc_id))
        else:
            print(f"Skipping {server_url} - no auth token")
            doc_ids.append((server_url, None))
    
    print("\n" + "=" * 50)
    print("Monitoring document processing...")
    print("=" * 50)
    
    # Monitor processing for each document
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        monitor_tasks = []
        for server_url, doc_id in doc_ids:
            if doc_id:
                token = auth_tokens[SERVERS.index(server_url)]
                future = executor.submit(monitor_document_processing, server_url, doc_id, token)
                monitor_tasks.append((server_url, doc_id, future))
        
        for server_url, doc_id, future in monitor_tasks:
            result = future.result()
            results.append((server_url, doc_id, result))
            print(f"\nServer {server_url}: Doc {doc_id} final result:")
            print(f"  Status: {result.get('status')}")
            print(f"  Full result: {result}")
            if result.get('status') == 'failed':
                error_msg = result.get('error') or result.get('error_message') or 'Unknown error'
                print(f"  Error: {error_msg}")
    
    print("\n" + "=" * 50)
    print("Load Test Summary")
    print("=" * 50)
    for server_url, doc_id, result in results:
        print(f"Server {server_url}: Document {doc_id} - {result.get('status')}")
    
    print("\nLoad test complete!")

if __name__ == "__main__":
    run_load_test()