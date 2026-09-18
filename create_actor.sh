#!/bin/bash
TOKEN=$(head -1 /tmp/apify_token.txt)

# Create actor with SOURCE_FILES sourceType (not GIT_REPO - that's broken)
curl -s -X POST "https://api.apify.com/v2/acts?token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mercari-scraper",
    "title": "Mercari USA Marketplace Scraper",
    "description": "Fast and reliable scraper for Mercari.com USA marketplace. Extract product listings with prices, conditions, images, and shipping info.",
    "isPublic": false,
    "seoTitle": "Mercari Scraper - USA Marketplace Product Data Extractor",
    "seoDescription": "Extract product listings from Mercari.com with prices, conditions, images, and shipping. Perfect for price monitoring and market research.",
    "versions": [{
      "versionNumber": "0.1",
      "sourceType": "SOURCE_FILES",
      "buildTag": "latest",
      "envVars": [],
      "applyEnvVarsToBuild": false
    }],
    "categories": ["ECOMMERCE"],
    "defaultRunOptions": {
      "build": "latest",
      "timeoutSecs": 300,
      "memoryMbytes": 1024
    }
  }' | jq -r '.data.id'
