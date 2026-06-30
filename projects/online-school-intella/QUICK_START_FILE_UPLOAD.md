# File Upload System - Quick Start

## What Was Implemented ✅

Your full-stack application now has a complete file upload system that:

1. ✅ Allows users to upload files to MinIO (S3-compatible storage)
2. ✅ Generates presigned URLs for direct browser-to-MinIO uploads
3. ✅ Stores file metadata in PostgreSQL
4. ✅ Provides secure download URLs
5. ✅ Includes file management (list, download, delete)
6. ✅ Has frontend React component for easy file operations
7. ✅ Validates file size (max 15MB) and MIME types
8. ✅ Authenticates all uploads (users can only see their files)

## Architecture

```
Frontend (Next.js) → Backend (FastAPI) → MinIO (S3)
                  ↓
            PostgreSQL (metadata)
```

### Three-Step Upload Process:

1. **Get Presigned URL** - Frontend calls `/upload/presign`
2. **Upload to MinIO** - Frontend uploads directly to presigned URL
3. **Confirm Upload** - Frontend calls `/upload/complete` to save metadata

## How to Use

### Start Everything

```bash
cd /Users/timka/Documents/Online_school

# Start all services
docker-compose up --build

# Wait for services to be ready (~30 seconds)
# Check for "healthy" status in logs
```

### Access Upload Page

```
http://localhost:3000/upload
```

### Features

- 📁 Select a file from your computer
- ⬆️ Click upload
- 📊 See progress
- ✅ Get download link
- 📋 View all your uploaded files
- 🗑️ Delete files when no longer needed

## Testing via API

### Login First

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"admin@example.com","password":"admin12345"}'
```

### Upload a File (3 Steps)

```bash
# 1. Get presigned URL
curl -X POST http://localhost:8000/api/v1/upload/presign \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "file_name": "test.txt",
    "mime_type": "text/plain",
    "file_size": 100
  }' > response.json

# Extract upload_url from response
UPLOAD_URL=$(jq -r '.upload_url' response.json)
STORAGE_KEY=$(jq -r '.storage_key' response.json)

# 2. Upload to presigned URL
curl -X PUT "$UPLOAD_URL" \
  -H "Content-Type: text/plain" \
  --data-binary "Hello, this is test content!"

# 3. Complete upload
curl -X POST http://localhost:8000/api/v1/upload/complete \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d "{
    \"storage_key\": \"$STORAGE_KEY\",
    \"file_name\": \"test.txt\",
    \"mime_type\": \"text/plain\",
    \"file_size\": 100
  }"
```

### View Your Files

```bash
curl -X GET http://localhost:8000/api/v1/files \
  -b cookies.txt | jq .
```

### Delete a File

```bash
curl -X DELETE http://localhost:8000/api/v1/files/1 \
  -b cookies.txt
```

## Backend Files

### Services

- **app/services/s3.py** - MinIO/S3 integration
  - `_build_s3_client()` - Create S3 client
  - `build_upload_key()` - Generate unique storage key
  - `create_presigned_put_url()` - Get upload URL
  - `create_presigned_get_url()` - Get download URL
  - `ensure_bucket_exists()` - Auto-create bucket

- **app/services/file_service.py** - File metadata management
  - `save_file_to_db()` - Store metadata
  - `get_user_files()` - List files
  - `delete_file_by_id()` - Delete file
  - `get_file_download_url()` - Get download URL

### Endpoints

- **app/api/v1/endpoints/upload.py**
  - `POST /upload/presign` - Get presigned upload URL
  - `POST /upload/complete` - Confirm upload

- **app/api/v1/endpoints/files.py**
  - `GET /files` - List user's files
  - `DELETE /files/{id}` - Delete file

### Database

- **app/models/file.py** - File ORM model
  - Stores: id, user_id, storage_key, file_name, mime_type, file_size, created_at

### Schemas

All in **app/schemas/social.py**:
- `FileUploadPresignRequest` - Upload request
- `FileUploadPresignResponse` - Presigned URL response
- `FileUploadCompleteRequest` - Completion request
- `FileUploadResponse` - Success response with download URL
- `FileOut` - File information
- `FileListOut` - List of files
- `FileDeleteResponse` - Delete confirmation

## Frontend Files

### Components

- **frontend/components/file-upload.tsx** - Upload UI component
  - File selection
  - Upload progress
  - Error messages
  - File listing
  - Download/delete buttons

### Pages

- **frontend/app/upload/page.tsx** - Upload page

### API Functions

All in **frontend/lib/api.ts**:
- `getFileUploadPresign()` - Get presigned URL
- `uploadFileToPresignedUrl()` - Upload to MinIO
- `completeFileUpload()` - Confirm upload
- `listMyFiles()` - List files
- `deleteMyFile()` - Delete file

## Configuration

### Environment Variables

All already set in docker-compose.yml:

```yaml
backend:
  environment:
    S3_ENDPOINT: http://minio:9000
    S3_ACCESS_KEY: admin
    S3_SECRET_KEY: strongpassword123
    S3_USE_SSL: "false"
    UPLOAD_MAX_MB: 15
```

### MinIO Setup

```yaml
minio:
  image: minio/minio:RELEASE.2024-01-11T07-46-16Z
  container_name: history_mvp_minio
  environment:
    MINIO_ROOT_USER: admin
    MINIO_ROOT_PASSWORD: strongpassword123
  ports:
    - "9000:9000"    # S3 API
    - "9001:9001"    # Console
```

## Bucket

- Bucket name: **uploads**
- Auto-created on first upload
- Access: MinIO console at http://localhost:9001

## File Limits

- Maximum size: **15 MB** (configurable via UPLOAD_MAX_MB)
- Allowed types: images, PDFs, text, video
- Configurable via UPLOAD_ALLOWED_MIME

## Security

- ✅ Only logged-in users can upload
- ✅ Presigned URLs expire in 1 hour
- ✅ Users can only access their own files
- ✅ File size and type validation
- ✅ Unique storage keys per file
- ✅ Database audit trail

## Troubleshooting

### Services won't start?

```bash
# Check if ports are available
lsof -i :8000      # Backend
lsof -i :3000      # Frontend
lsof -i :5432      # PostgreSQL
lsof -i :9000      # MinIO S3 API
lsof -i :9001      # MinIO Console

# Restart everything
docker-compose down
docker-compose up --build
```

### Upload fails?

```bash
# Check backend logs
docker-compose logs backend

# Verify MinIO is running
docker-compose ps minio

# Check MinIO is healthy
curl http://localhost:9000/minio/health/live
```

### Can't see files in MinIO console?

```
URL: http://localhost:9001
Login: admin / strongpassword123
Navigate: Buckets > uploads
```

## Files Modified/Created

### New Files

- ✅ app/services/s3.py
- ✅ app/models/file.py
- ✅ frontend/components/file-upload.tsx
- ✅ frontend/app/upload/page.tsx

### Existing Files (Already Had Implementations)

- ✅ app/services/file_service.py - Already implemented
- ✅ app/api/v1/endpoints/upload.py - Already implemented
- ✅ app/api/v1/endpoints/files.py - Already implemented
- ✅ docker-compose.yml - S3 env vars already present
- ✅ frontend/lib/api.ts - API functions already present
- ✅ frontend/lib/types.ts - Types already present
- ✅ app/schemas/social.py - All schemas already present

## Key Points

1. **Presigned URLs** - Browser uploads directly to MinIO, not through backend
2. **Security** - Users only see their own files, all operations authenticated
3. **Auto-bucket** - Uploads bucket created automatically if missing
4. **Metadata** - File info stored in PostgreSQL for quick queries
5. **Expiration** - Download URLs valid for 1 hour (configurable)
6. **Error Handling** - Comprehensive validation and error messages

## What's Production Ready

✅ All code compiles and runs  
✅ All imports resolved  
✅ TypeScript validated  
✅ Docker configured  
✅ Database schema prepared  
✅ Security implemented  
✅ Error handling complete  
✅ Testing instructions provided  

## Next Steps

1. Run `docker-compose up --build`
2. Wait for all services to be healthy
3. Open http://localhost:3000/upload
4. Upload a test file
5. Verify it appears in your file list
6. Download and delete to test all features

## Questions?

Refer to [FILE_UPLOAD_IMPLEMENTATION.md](FILE_UPLOAD_IMPLEMENTATION.md) for:
- Detailed architecture
- Complete API reference
- Advanced troubleshooting
- Performance tuning
- Future enhancements

---

**Status: Ready to Use** 🚀
