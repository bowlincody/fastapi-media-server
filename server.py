from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import boto3

app = FastAPI()

# Local storage setup
UPLOAD_FOLDER = "media"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# AWS S3 Configuration (Read from Environment Variables)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "media-uploader-dev-us-east-microlumix-001")

# Create S3 Client
if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    raise RuntimeError("AWS credentials are missing! Check environment variables.")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


clients = []  # List of connected WebSocket clients


# Upload a media file (Local Storage)
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """ Uploads a file to local storage and notifies clients via WebSocket """
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    
    # Stream file to avoid memory overload
    with open(file_path, "wb") as buffer:
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""): # Read 1MB at a time
            buffer.write(chunk)

    # Notify all connected WebSocket clients about the new file
    for client in clients:
        await client.send_json({"message": "new_file", "filename": file.filename})

    return {"message": "File uploaded successfully", "filename": file.filename}


# Generate Pre-Signed URL for S3 Upload
@app.get("/generate-presigned-url")
def generate_presigned_url(file_name: str = Query(..., description="Name of the file to be uploaded")):
    """
    Generates a pre-signed URL for direct file uploads to S3.
    """
    try:
        presigned_post = s3_client.generate_presigned_post(
            Bucket=BUCKET_NAME,
            Key=file_name,
            Fields=None,
            Conditions=None,
            ExpiresIn=3600  # URL expires in 1 hour
        )
    except Exception as e:
        print(f"Error generating pre-signed URL: {e}") # Logs error
        raise HTTPException(status_code=500, detail="Could not generate upload URL. Please try again later.")

    return JSONResponse(content=presigned_post)


# List all media files (Local Storage)
@app.get("/list")
def list_files():
    files = os.listdir(UPLOAD_FOLDER)
    return {"files": files}


# WebSocket for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection open
    except Exception as e:
        print(f"WebSocket disconnected: {e}") # Log the error
    finally:
        clients.remove(websocket) # Ensure client is removed when they disconnect


# Download a media file (Local Storage)
@app.get("/media/{filename}")
def get_file(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


# Health check endpoint
@app.get("/")
def read_root():
    return {"message": "Media Server is Running"}


# Delete a file (Local Storage)
@app.delete("/delete/{filename}")
def delete_file(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)
    return {"message": "File deleted successfully", "filename": filename}


# CORS Configuration (Allows communication with frontends like React, Flutter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
