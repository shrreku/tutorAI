#!/bin/bash
# Ingest a PDF via the API

API_URL="${API_URL:-http://localhost:8000}"
PDF_PATH="${1:-/Users/shreyashkumar/coding/projects/StudyAgent/tutorAI/notes/MTL106 Lec 1-6.pdf}"

echo "=============================================="
echo "StudyAgent Ingestion via API"
echo "=============================================="
echo "API URL: $API_URL"
echo "PDF: $PDF_PATH"
echo ""

# Check if PDF exists
if [ ! -f "$PDF_PATH" ]; then
    echo "ERROR: PDF file not found: $PDF_PATH"
    exit 1
fi

# Step 1: List and delete existing resources
echo "Step 1: Cleaning up existing resources..."
RESOURCES=$(curl -s "$API_URL/api/v1/resources" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join([str(r['id']) for r in d.get('items',[])]))" 2>/dev/null)

if [ -n "$RESOURCES" ]; then
    for rid in $RESOURCES; do
        echo "  Deleting resource: $rid"
        curl -s -X DELETE "$API_URL/api/v1/resources/$rid" > /dev/null
    done
    echo "  Deleted all existing resources."
else
    echo "  No existing resources found."
fi

# Step 2: Upload PDF for ingestion
echo ""
echo "Step 2: Uploading PDF for ingestion..."
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/ingest/upload" \
    -F "file=@$PDF_PATH" \
    -F "topic=Probability and Statistics")

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)
RESOURCE_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('resource_id',''))" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to start ingestion"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "  Job ID: $JOB_ID"
echo "  Resource ID: $RESOURCE_ID"

# Step 3: Poll for status
echo ""
echo "Step 3: Monitoring ingestion progress..."
echo "=============================================="

while true; do
    STATUS_RESPONSE=$(curl -s "$API_URL/api/v1/ingest/status/$JOB_ID")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
    STAGE=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_stage',''))" 2>/dev/null)
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress_percent',0))" 2>/dev/null)
    ERROR=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_message','') or '')" 2>/dev/null)
    
    echo "[$(date +%H:%M:%S)] Status: $STATUS | Stage: $STAGE | Progress: $PROGRESS%"
    
    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo "=============================================="
        echo "INGESTION COMPLETED SUCCESSFULLY"
        echo "=============================================="
        break
    elif [ "$STATUS" = "failed" ]; then
        echo ""
        echo "=============================================="
        echo "INGESTION FAILED"
        echo "Error: $ERROR"
        echo "=============================================="
        exit 1
    fi
    
    sleep 5
done

# Step 4: Show resource details
echo ""
echo "Step 4: Resource Details"
echo "=============================================="
curl -s "$API_URL/api/v1/resources/$RESOURCE_ID" | python3 -m json.tool

echo ""
echo "Done!"
