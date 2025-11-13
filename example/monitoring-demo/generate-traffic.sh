#!/bin/bash
# Generate test traffic to the FastAPI endpoint

set -e

if [ -z "$FASTAPI_URL" ]; then
    echo "❌ Error: FASTAPI_URL environment variable is not set"
    echo "Please run: export FASTAPI_URL=your-fastapi-url"
    exit 1
fi

echo "🚀 Generating test traffic to $FASTAPI_URL"
echo "📊 Sending 100 predictions..."
echo ""

for i in {1..100}; do
    BEDROOMS=$((RANDOM % 5 + 1))
    BATHROOMS=$((RANDOM % 3 + 1))
    SQFT=$((RANDOM % 3000 + 1000))
    AGE=$((RANDOM % 40))
    
    RESPONSE=$(curl -s -X POST "${FASTAPI_URL}/predict" \
        -H "Content-Type: application/json" \
        -d "{
            \"bedrooms\": $BEDROOMS,
            \"bathrooms\": $BATHROOMS,
            \"sqft\": $SQFT,
            \"age\": $AGE
        }")
    
    PREDICTION=$(echo $RESPONSE | grep -o '"prediction":[0-9.]*' | grep -o '[0-9.]*')
    
    if [ $((i % 10)) -eq 0 ]; then
        echo "  [$i/100] Prediction: \$$PREDICTION"
    fi
    
    sleep 0.2
done

echo ""
echo "✅ Generated 100 predictions!"
echo ""
echo "Check stats: curl ${FASTAPI_URL}/stats"

