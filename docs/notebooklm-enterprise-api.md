# NotebookLM Enterprise API Documentation

## Overview

NotebookLM Enterprise API allows you to programmatically manage notebooks and data sources. This document describes how to interact with the API.

## Base URL

```
https://ENDPOINT_LOCATION-discoveryengine.googleapis.com/v1alpha
```

Where `ENDPOINT_LOCATION` is one of:
- `us-` for the US multi-region
- `eu-` for the EU multi-region
- `global-` for the Global location

## Authentication

All API requests require authentication using Google Cloud credentials:

```bash
gcloud auth login --enable-gdrive-access
```

Then use the access token:
```bash
gcloud auth print-access-token
```

## Endpoints

### Add Data Sources in Batch

**Endpoint:** `POST /projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/sources:batchCreate`

**Request Body:**
```json
{
  "userContents": [
    {
      "googleDriveContent": {
        "documentId": "DOCUMENT_ID_GOOGLE",
        "mimeType": "MIME_TYPE",
        "sourceName": "DISPLAY_NAME_GOOGLE"
      }
    }
  ]
}
```

Or for raw text:
```json
{
  "userContents": [
    {
      "textContent": {
        "sourceName": "DISPLAY_NAME_TEXT",
        "content": "TEXT_CONTENT"
      }
    }
  ]
}
```

Or for web content:
```json
{
  "userContents": [
    {
      "webContent": {
        "url": "URL_WEBCONTENT",
        "sourceName": "DISPLAY_NAME_WEB"
      }
    }
  ]
}
```

Or for video content:
```json
{
  "userContents": [
    {
      "videoContent": {
        "url": "URL_YOUTUBE"
      }
    }
  ]
}
```

**Response:**
```json
{
  "sources": [
    {
      "sourceId": {
        "id": "SOURCE_ID"
      },
      "title": "DISPLAY_NAME",
      "metadata": {
        "xyz": "abc"
      },
      "settings": {
        "status": "SOURCE_STATUS_COMPLETE"
      },
      "name": "SOURCE_RESOURCE_NAME"
    }
  ]
}
```

### Upload a File as Source

**Endpoint:** `POST /upload/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/sources:uploadFile`

**Headers:**
- `Authorization: Bearer {ACCESS_TOKEN}`
- `X-Goog-Upload-File-Name: FILE_DISPLAY_NAME`
- `X-Goog-Upload-Protocol: raw`
- `Content-Type: CONTENT_TYPE`

**Request:** Binary file data

**Response:**
```json
{
  "sourceId": {
    "id": "SOURCE_ID"
  }
}
```

### Retrieve a Source

**Endpoint:** `GET /projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/sources/{SOURCE_ID}`

**Response:**
```json
{
  "sources": [
    {
      "sourceId": {
        "id": "SOURCE_ID"
      },
      "title": "DISPLAY_NAME",
      "metadata": {
        "wordCount": 148,
        "tokenCount": 160
      },
      "settings": {
        "status": "SOURCE_STATUS_COMPLETE"
      },
      "name": "SOURCE_RESOURCE_NAME"
    }
  ]
}
```

### Delete Data Sources

**Endpoint:** `POST /projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/sources:batchDelete`

**Request Body:**
```json
{
  "names": [
    "SOURCE_RESOURCE_NAME_1",
    "SOURCE_RESOURCE_NAME_2"
  ]
}
```

**Response:** Empty JSON object `{}`

## Supported Content Types

### Documents
- `.pdf` - `application/pdf`
- `.txt` - `text/plain`
- `.md` - `text/markdown`
- `.docx` - `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `.pptx` - `application/vnd.openxmlformats-officedocument.presentationml.presentation`
- `.xlsx` - `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### Audio
- `.mp3` - `audio/mpeg`
- `.wav` - `audio/wav`
- `.m4a` - `audio/m4a`
- And many more...

### Images
- `.png` - `image/png`
- `.jpg` / `.jpeg` - `image/jpeg`

## Query a Notebook

To query a notebook (ask questions), you would typically use the chat/completion endpoint. The exact endpoint may vary, but it's typically:

**Endpoint:** `POST /projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}:query`

**Request Body:**
```json
{
  "query": "YOUR_QUESTION_HERE"
}
```

**Response:**
```json
{
  "response": "ANSWER_FROM_NOTEBOOK",
  "sources": [...]
}
```

## Parameters

- **PROJECT_NUMBER**: The number of your Google Cloud project
- **LOCATION**: The geographic location (e.g., `global`)
- **NOTEBOOK_ID**: The unique identifier of the notebook
- **SOURCE_ID**: The source's identifier
- **SOURCE_RESOURCE_NAME**: Full resource name pattern: `projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/source/{SOURCE_ID}`

