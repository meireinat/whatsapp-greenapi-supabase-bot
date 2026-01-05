"""
Web chat interface for querying the bot.
"""

from __future__ import annotations

import logging
import datetime as dt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.constants import (
    MAX_CONVERSATION_HISTORY,
    DEFAULT_METRICS_YEARS_BACK,
    DEFAULT_MAX_ROWS_FOR_LLM,
    VERSION,
)
from app.services.intent_engine import IntentEngine, IntentResult
from app.services.response_builder import (
    build_containers_range_response,
    build_daily_containers_response,
    build_fallback_response,
    build_monthly_containers_response,
    build_comparison_containers_response,
    build_vehicles_range_response,
    build_container_status_response,
)
from app.services.supabase_client import SupabaseService
from app.services.gemini_client import GeminiService
from app.services.council_client import CouncilService
from app.services.hazard_knowledge import HazardKnowledgeBase
from app.services.topic_knowledge import TopicKnowledgeBase
from app.services.container_status import ContainerStatusService
from app.services.manager_gpt_service import ManagerGPTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request model for chat queries."""
    question: str
    user_id: str | None = None  # Optional user ID for conversation history


class Citation(BaseModel):
    """Model for document citation."""
    document_title: str | None = None
    source_file: str | None = None
    excerpt: str
    section_id: str | None = None


class ChatResponse(BaseModel):
    """Response model for chat queries."""
    answer: str
    intent: str | None = None
    citations: list[Citation] | None = None


class RecentQuery(BaseModel):
    """Model for recent query."""
    id: int
    user_text: str
    response_text: str | None = None
    intent: str | None = None
    created_at: str


class RecentQueriesResponse(BaseModel):
    """Response model for recent queries."""
    queries: list[RecentQuery]


def get_intent_engine() -> IntentEngine:
    from app.main import app
    return getattr(app.state, "intent_engine", None)


def get_supabase_service() -> SupabaseService:
    from app.main import app
    return getattr(app.state, "supabase_service", None)


def get_gemini_service() -> GeminiService | None:
    from app.main import app
    return getattr(app.state, "gemini_service", None)


def get_council_service() -> CouncilService | None:
    from app.main import app
    return getattr(app.state, "council_service", None)


def get_hazard_knowledge() -> HazardKnowledgeBase | None:
    from app.main import app
    return getattr(app.state, "hazard_knowledge", None)


def get_topic_knowledge() -> TopicKnowledgeBase | None:
    from app.main import app
    return getattr(app.state, "topic_knowledge", None)


def get_container_status_service() -> ContainerStatusService | None:
    from app.main import app
    return getattr(app.state, "container_status_service", None)


def get_manager_gpt_service() -> ManagerGPTService | None:
    from app.main import app
    return getattr(app.state, "manager_gpt_service", None)


def get_version() -> str:
    """Get application version from constants."""
    # VERSION in constants.py should be updated by update_version.py script
    # or CI/CD pipeline to include commit hash
    return VERSION


@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)  # Also handle URL without trailing slash
async def chat_page():
    """Serve the chat interface HTML page."""
    version = get_version()
    html_content = """
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚓ בוט נמלי - צ'אט</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .chat-container {
            width: 100%;
            max-width: 800px;
            height: 90vh;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        
        .chat-header-title {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .chat-header-version {
            font-size: 12px;
            opacity: 0.8;
            font-weight: normal;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f5f5f5;
        }
        
        .message {
            margin-bottom: 15px;
            display: flex;
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .message.user {
            justify-content: flex-end;
        }
        
        .message.bot {
            justify-content: flex-start;
        }
        
        .message-content {
            max-width: 70%;
            padding: 12px 18px;
            border-radius: 18px;
            word-wrap: break-word;
            white-space: pre-wrap;
        }
        
        .message.user .message-content {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.bot .message-content {
            background: white;
            color: #333;
            border: 1px solid #e0e0e0;
            border-bottom-left-radius: 4px;
        }
        
        .chat-input-container {
            padding: 20px;
            background: white;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 10px;
        }
        
        .chat-input {
            flex: 1;
            padding: 12px 18px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.3s;
        }
        
        .chat-input:focus {
            border-color: #667eea;
        }
        
        .send-button {
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .send-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .send-button:active {
            transform: translateY(0);
        }
        
        .send-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .voice-button {
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 50%;
            min-width: 48px;
            width: 48px;
            min-height: 48px;
            height: 48px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .voice-button {
            font-size: 20px;
            line-height: 1;
        }
        
        .voice-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .voice-button:active {
            transform: translateY(0);
        }
        
        .voice-button.recording {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
            animation: pulse 1.5s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% {
                transform: scale(1);
            }
            50% {
                transform: scale(1.1);
            }
        }
        
        .voice-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .welcome-message {
            text-align: center;
            color: #666;
            padding: 20px;
            font-size: 16px;
            margin-bottom: 15px;
        }
        
        .message-content {
            display: block;
            visibility: visible;
            opacity: 1;
        }
        
        .citations {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e0e0e0;
        }
        
        .citations-title {
            font-size: 12px;
            font-weight: bold;
            color: #666;
            margin-bottom: 10px;
        }
        
        .citation-item {
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            font-size: 13px;
        }
        
        .citation-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .citation-document {
            font-weight: bold;
            color: #667eea;
            font-size: 14px;
        }
        
        .citation-source {
            font-size: 11px;
            color: #999;
        }
        
        .citation-excerpt {
            color: #555;
            line-height: 1.5;
            font-style: italic;
            border-right: 3px solid #667eea;
            padding-right: 10px;
            margin-top: 8px;
        }
        
        .recent-queries-panel {
            position: fixed;
            top: 0;
            right: 0;
            width: 300px;
            max-width: 90vw;
            height: 100vh;
            background: white;
            box-shadow: -2px 0 10px rgba(0, 0, 0, 0.1);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            z-index: 1000;
            overflow-y: auto;
            padding: 20px;
        }
        
        .recent-queries-panel.open {
            transform: translateX(0);
        }
        
        .recent-queries-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e0e0e0;
        }
        
        .recent-queries-header h2 {
            margin: 0;
            font-size: 18px;
            color: #333;
        }
        
        .close-panel {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #666;
            padding: 0;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .query-item {
            padding: 12px;
            margin-bottom: 12px;
            background: #f5f5f5;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }
        
        .query-text {
            font-size: 14px;
            color: #333;
            margin-bottom: 8px;
            word-wrap: break-word;
        }
        
        .query-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        
        .query-action-btn {
            padding: 6px 12px;
            font-size: 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            background: #667eea;
            color: white;
            transition: background 0.2s;
        }
        
        .query-action-btn:hover {
            background: #5568d3;
        }
        
        .query-action-btn.copy {
            background: #4caf50;
        }
        
        .query-action-btn.copy:hover {
            background: #45a049;
        }
        
        .query-action-btn.edit {
            background: #ff9800;
        }
        
        .query-action-btn.edit:hover {
            background: #f57c00;
        }
        
        .toggle-queries-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            font-size: 20px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: 999;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .toggle-queries-btn:hover {
            transform: scale(1.1);
        }
        
        /* Mobile responsive styles */
        @media (max-width: 768px) {
            .send-button {
                padding: 10px 20px;
                font-size: 14px;
            }
            
            .voice-button {
                width: 44px;
                height: 44px;
                min-width: 44px;
                min-height: 44px;
                padding: 10px;
            }
            
            .chat-input-container {
                padding: 15px;
                gap: 8px;
            }
            
            .chat-input {
                font-size: 14px;
                padding: 10px 15px;
            }
        }
        
        @media (max-width: 480px) {
            .send-button {
                padding: 8px 15px;
                font-size: 12px;
            }
            
            .voice-button {
                width: 40px;
                height: 40px;
                min-width: 40px;
                min-height: 40px;
                padding: 8px;
            }
            
            .chat-input-container {
                padding: 12px;
                gap: 6px;
            }
            
            .chat-input {
                font-size: 14px;
                padding: 8px 12px;
            }
            
            .recent-queries-panel {
                width: 100vw;
            }
            
            .toggle-queries-btn {
                width: 48px;
                height: 48px;
                bottom: 15px;
                right: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <div class="chat-header-title">
                ⚓ בוט נמלי
            </div>
            <div class="chat-header-version">גרסה """ + version + """</div>
        </div>
        <div class="chat-messages" id="messages">
            <div class="welcome-message">
                שלום! אני בוט נמלי. איך אוכל לעזור לך היום?
            </div>
        </div>
        <div class="chat-input-container">
            <input 
                type="text" 
                id="questionInput" 
                class="chat-input" 
                placeholder="הקלד את השאלה שלך כאן..."
                autocomplete="off"
            />
            <button id="voiceButton" class="voice-button" title="דיבור" type="button" aria-label="דיבור">🎤</button>
            <button id="sendButton" class="send-button">שלח</button>
        </div>
    </div>
    
    <!-- Recent Queries Panel -->
    <button id="toggleQueriesBtn" class="toggle-queries-btn" title="שאלות אחרונות">📋</button>
    <div id="recentQueriesPanel" class="recent-queries-panel">
        <div class="recent-queries-header">
            <h2>10 שאלות אחרונות</h2>
            <button class="close-panel" id="closePanelBtn">×</button>
        </div>
        <div id="queriesList"></div>
    </div>
    
    <script>
        const messagesContainer = document.getElementById('messages');
        const questionInput = document.getElementById('questionInput');
        const sendButton = document.getElementById('sendButton');
        const voiceButton = document.getElementById('voiceButton');
        
        // Check if Web Speech API is supported
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recognition = null;
        let isRecording = false;
        
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.lang = 'he-IL'; // Hebrew (Israel)
            recognition.continuous = false;
            recognition.interimResults = false;
            
            recognition.onstart = function() {
                isRecording = true;
                voiceButton.classList.add('recording');
                voiceButton.title = 'מקליט... לחץ שוב כדי לעצור';
            };
            
            recognition.onresult = function(event) {
                const transcript = event.results[0][0].transcript;
                questionInput.value = transcript;
                questionInput.focus();
                stopRecording();
            };
            
            recognition.onerror = function(event) {
                console.error('Speech recognition error:', event.error);
                stopRecording();
                if (event.error === 'no-speech') {
                    alert('לא זוהה דיבור. נסה שוב.');
                } else if (event.error === 'not-allowed') {
                    alert('גישה למיקרופון נדחתה. אנא אפשר גישה למיקרופון בדפדפן.');
                } else {
                    alert('שגיאה בהכרת דיבור: ' + event.error);
                }
            };
            
            recognition.onend = function() {
                stopRecording();
            };
        } else {
            voiceButton.disabled = true;
            voiceButton.title = 'הכרת דיבור לא נתמכת בדפדפן זה';
        }
        
        function startRecording() {
            if (!recognition || isRecording) {
                return;
            }
            try {
                recognition.start();
            } catch (e) {
                console.error('Error starting recognition:', e);
            }
        }
        
        function stopRecording() {
            if (!recognition || !isRecording) {
                return;
            }
            try {
                recognition.stop();
            } catch (e) {
                console.error('Error stopping recognition:', e);
            }
            isRecording = false;
            voiceButton.classList.remove('recording');
            voiceButton.title = 'דיבור';
        }
        
        voiceButton.addEventListener('click', function() {
            if (isRecording) {
                stopRecording();
            } else {
                startRecording();
            }
        });
        
        function addMessage(text, isUser, citations = null) {
            console.log('Adding message:', text, 'isUser:', isUser, 'citations:', citations);
            
            // Remove welcome message if exists (do this first)
            const welcomeMsg = messagesContainer.querySelector('.welcome-message');
            if (welcomeMsg) {
                console.log('Removing welcome message');
                welcomeMsg.remove();
            }
            
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = text;
            
            messageDiv.appendChild(contentDiv);
            
            // Add citations if available
            if (citations && citations.length > 0 && !isUser) {
                const citationsDiv = document.createElement('div');
                citationsDiv.className = 'citations';
                
                const citationsTitle = document.createElement('div');
                citationsTitle.className = 'citations-title';
                citationsTitle.textContent = 'מקורות:';
                citationsDiv.appendChild(citationsTitle);
                
                citations.forEach((citation, index) => {
                    const citationItem = document.createElement('div');
                    citationItem.className = 'citation-item';
                    
                    const citationHeader = document.createElement('div');
                    citationHeader.className = 'citation-header';
                    
                    const documentName = document.createElement('div');
                    documentName.className = 'citation-document';
                    documentName.textContent = citation.document_title || citation.source_file || `מקור ${index + 1}`;
                    citationHeader.appendChild(documentName);
                    
                    if (citation.source_file) {
                        const sourceFile = document.createElement('div');
                        sourceFile.className = 'citation-source';
                        sourceFile.textContent = citation.source_file;
                        citationHeader.appendChild(sourceFile);
                    }
                    
                    citationItem.appendChild(citationHeader);
                    
                    if (citation.excerpt) {
                        const excerpt = document.createElement('div');
                        excerpt.className = 'citation-excerpt';
                        excerpt.textContent = citation.excerpt;
                        citationItem.appendChild(excerpt);
                    }
                    
                    citationsDiv.appendChild(citationItem);
                });
                
                messageDiv.appendChild(citationsDiv);
            }
            
            messagesContainer.appendChild(messageDiv);
            console.log('Message added to DOM, container has', messagesContainer.children.length, 'children');
            
            // Force a reflow to ensure the message is visible
            void messageDiv.offsetHeight;
            
            // Scroll to bottom
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            console.log('Scrolled to', messagesContainer.scrollTop, 'of', messagesContainer.scrollHeight);
        }
        
        function showLoading() {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message bot';
            messageDiv.id = 'loading-message';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.innerHTML = '<div class="loading"></div>';
            
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        function removeLoading() {
            const loadingMsg = document.getElementById('loading-message');
            if (loadingMsg) {
                loadingMsg.remove();
            }
        }
        
        async function sendMessage() {
            const question = questionInput.value.trim();
            if (!question) {
                return;
            }
            
            // Add user message
            addMessage(question, true);
            questionInput.value = '';
            sendButton.disabled = true;
            sendButton.innerHTML = '<div class="loading"></div>';
            
            // Show loading
            showLoading();
            
            try {
                console.log('Sending request with question:', question);
                const response = await fetch('/api/chat/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ question: question })
                });
                
                console.log('Response status:', response.status, response.statusText);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('API Error:', response.status, errorText);
                    throw new Error(`שגיאה ${response.status}: ${errorText.substring(0, 100)}`);
                }
                
                const data = await response.json();
                console.log('Response data:', data);
                console.log('Response answer:', data.answer);
                removeLoading();
                
                if (!data || !data.answer) {
                    console.error('Invalid response format:', data);
                    throw new Error('תשובה לא תקינה מהשרת');
                }
                
                console.log('Calling addMessage with:', data.answer);
                addMessage(data.answer, false, data.citations);
                console.log('Message should be displayed now');
            } catch (error) {
                removeLoading();
                console.error('Error in sendMessage:', error);
                console.error('Error stack:', error.stack);
                const errorMsg = error.message || 'מצטער, אירעה שגיאה. אנא נסה שוב מאוחר יותר.';
                addMessage(errorMsg, false);
            } finally {
                sendButton.disabled = false;
                sendButton.textContent = 'שלח';
                questionInput.focus();
            }
        }
        
        sendButton.addEventListener('click', sendMessage);
        
        questionInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !sendButton.disabled) {
                sendMessage();
            }
        });
        
        // Focus input on load
        questionInput.focus();
        
        // Recent Queries Panel
        const toggleQueriesBtn = document.getElementById('toggleQueriesBtn');
        const recentQueriesPanel = document.getElementById('recentQueriesPanel');
        const closePanelBtn = document.getElementById('closePanelBtn');
        const queriesList = document.getElementById('queriesList');
        
        toggleQueriesBtn.addEventListener('click', function() {
            console.log('Toggle button clicked');
            const wasOpen = recentQueriesPanel.classList.contains('open');
            recentQueriesPanel.classList.toggle('open');
            
            // Always reload queries when opening the panel (even if it was already open)
            if (recentQueriesPanel.classList.contains('open')) {
                console.log('Loading recent queries from DB...');
                loadRecentQueries();
            }
        });
        
        closePanelBtn.addEventListener('click', function() {
            recentQueriesPanel.classList.remove('open');
        });
        
        async function loadRecentQueries() {
            // Show loading state
            queriesList.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">טוען שאלות מהמסד נתונים...</p>';
            
            try {
                // Add timestamp to prevent caching
                const response = await fetch('/api/chat/recent-queries?t=' + Date.now());
                if (!response.ok) {
                    throw new Error('Failed to load queries');
                }
                const data = await response.json();
                console.log('Loaded queries from DB:', data.queries.length);
                displayQueries(data.queries);
            } catch (error) {
                console.error('Error loading recent queries:', error);
                queriesList.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 20px;">שגיאה בטעינת השאלות מהמסד נתונים</p>';
            }
        }
        
        function displayQueries(queries) {
            if (queries.length === 0) {
                queriesList.innerHTML = '<p style="color: #999; text-align: center;">אין שאלות אחרונות</p>';
                return;
            }
            
            queriesList.innerHTML = queries.map((query, index) => {
                const escapedText = escapeHtml(query.user_text);
                return `
                <div class="query-item">
                    <div class="query-text">${escapedText}</div>
                    <div class="query-actions">
                        <button class="query-action-btn copy" onclick="copyQuery(${index})">העתק</button>
                        <button class="query-action-btn edit" onclick="editQuery(${index})">ערוך</button>
                        <button class="query-action-btn" onclick="askAgain(${index})">שאל שוב</button>
                    </div>
                </div>
            `;
            }).join('');
            
            // Store queries in a global variable for button handlers
            window.recentQueries = queries;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        window.copyQuery = function(index) {
            const query = window.recentQueries[index];
            navigator.clipboard.writeText(query.user_text).then(() => {
                alert('השאלה הועתקה ללוח');
            }).catch(err => {
                console.error('Failed to copy:', err);
                alert('שגיאה בהעתקה');
            });
        };
        
        window.editQuery = function(index) {
            const query = window.recentQueries[index];
            questionInput.value = query.user_text;
            questionInput.focus();
            recentQueriesPanel.classList.remove('open');
        };
        
        window.askAgain = function(index) {
            const query = window.recentQueries[index];
            questionInput.value = query.user_text;
            questionInput.focus();
            recentQueriesPanel.classList.remove('open');
            sendMessage();
        };
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    intent_engine: IntentEngine = Depends(get_intent_engine),
    supabase_service: SupabaseService = Depends(get_supabase_service),
    gemini_service: GeminiService | None = Depends(get_gemini_service),
    council_service: CouncilService | None = Depends(get_council_service),
    hazard_knowledge: HazardKnowledgeBase | None = Depends(get_hazard_knowledge),
    topic_knowledge: TopicKnowledgeBase | None = Depends(get_topic_knowledge),
    container_status_service: ContainerStatusService | None = Depends(get_container_status_service),
    manager_gpt_service: ManagerGPTService | None = Depends(get_manager_gpt_service),
) -> ChatResponse:
    """
    Handle chat queries and return responses.
    Uses the same logic as the webhook handler but without Green API.
    """
    import datetime as dt
    
    try:
        incoming_text = request.question.strip()
        if not incoming_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")
        
        logger.info("Chat query received: %s", incoming_text)
        
        # Use user_id if provided, otherwise use a default
        user_id = request.user_id or "web_user"
        chat_id = f"{user_id}@web"
        
        # Match intent
        intent: IntentResult | None = intent_engine.match(incoming_text)
        logger.info("Intent matched: %s (parameters: %s)", intent.name if intent else "None", intent.parameters if intent else "None")
        
        # Get conversation history if user_id is provided
        conversation_history = None
        if request.user_id:
            conversation_history = supabase_service.get_recent_user_queries(
                user_phone=chat_id,
                limit=MAX_CONVERSATION_HISTORY,
                exclude_current=True,
            )
            if conversation_history:
                logger.info("Retrieved %d previous queries for context", len(conversation_history))
        
        # Get knowledge sections
        hazard_sections = (
            hazard_knowledge.build_sections(incoming_text)
            if hazard_knowledge and hazard_knowledge.is_available()
            else None
        )
        
        topic_sections = (
            topic_knowledge.build_sections(incoming_text)
            if topic_knowledge and topic_knowledge.is_available()
            else None
        )
        
        knowledge_sections = []
        if hazard_sections:
            knowledge_sections.extend(hazard_sections)
        if topic_sections:
            knowledge_sections.extend(topic_sections)
        
        combined_knowledge = knowledge_sections if knowledge_sections else None
        
        response_text = ""
        intent_name = None
        citations_list = []
        used_knowledge = False  # Track if knowledge sections were used in the response
        
        if not intent:
            logger.info("No intent matched, using Council/Gemini or fallback")
            end_date = dt.date.today()
            start_date = dt.date(end_date.year - DEFAULT_METRICS_YEARS_BACK, 1, 1)
            metrics = supabase_service.get_metrics_summary(
                start_date=start_date,
                end_date=end_date,
                max_rows=DEFAULT_MAX_ROWS_FOR_LLM,
            )
            
            try:
                if council_service:
                    logger.info("Using Council service...")
                    response_text = await council_service.answer_question(
                        question=incoming_text,
                        metrics=metrics,
                        knowledge_sections=combined_knowledge,
                        conversation_history=conversation_history,
                    )
                    # If knowledge sections were provided and used, mark as used
                    if combined_knowledge:
                        used_knowledge = True
                elif gemini_service:
                    logger.info("Using Gemini service...")
                    response_text = await gemini_service.answer_question(
                        question=incoming_text,
                        metrics=metrics,
                        knowledge_sections=combined_knowledge,
                        conversation_history=conversation_history,
                    )
                    # If knowledge sections were provided and used, mark as used
                    if combined_knowledge:
                        used_knowledge = True
                else:
                    logger.info("No LLM service available, using fallback")
                    response_text = build_fallback_response()
            except Exception as e:
                logger.error("Error calling LLM service: %s", e, exc_info=True)
                response_text = build_fallback_response()
            
            if not response_text or not response_text.strip():
                response_text = build_fallback_response()
        else:
            intent_name = intent.name
            
            # Handle different intents
            if intent.name == "containers_count_monthly":
                month = intent.parameters.get("month")
                year = intent.parameters.get("year")
                if month and year:
                    try:
                        count = supabase_service.get_containers_count_monthly(month=month, year=year)
                        response_text = build_monthly_containers_response(month=month, year=year, count=count)
                    except Exception as e:
                        logger.error("Error getting monthly container count: %s", e, exc_info=True)
                        response_text = build_fallback_response()
                else:
                    logger.warning("Missing month or year parameters for containers_count_monthly")
                    response_text = build_fallback_response()
            
            elif intent.name == "containers_count_daily":
                date = intent.parameters.get("date")
                if date:
                    count = supabase_service.get_daily_container_count(date=date)
                    response_text = build_daily_containers_response(date=date, count=count)
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "containers_count_range":
                start_date = intent.parameters.get("start_date")
                end_date = intent.parameters.get("end_date")
                if start_date and end_date:
                    count = supabase_service.get_container_count_range(start_date=start_date, end_date=end_date)
                    response_text = build_containers_range_response(start_date=start_date, end_date=end_date, count=count)
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "containers_comparison":
                start_date = intent.parameters.get("start_date")
                end_date = intent.parameters.get("end_date")
                if start_date and end_date:
                    count1 = supabase_service.get_container_count_range(
                        start_date=start_date, end_date=start_date
                    )
                    count2 = supabase_service.get_container_count_range(
                        start_date=end_date, end_date=end_date
                    )
                    response_text = build_comparison_containers_response(
                        date1=start_date, count1=count1, date2=end_date, count2=count2
                    )
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "vehicles_count_range":
                start_date = intent.parameters.get("start_date")
                end_date = intent.parameters.get("end_date")
                if start_date and end_date:
                    count = supabase_service.get_vehicle_count_range(start_date=start_date, end_date=end_date)
                    response_text = build_vehicles_range_response(start_date=start_date, end_date=end_date, count=count)
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "container_status_lookup":
                container_id = intent.parameters.get("container_id")
                if container_id and container_status_service:
                    try:
                        statuses = await container_status_service.lookup(container_id)
                        response_text = build_container_status_response(container_id, statuses)
                    except Exception as e:
                        logger.error("Error getting container status: %s", e, exc_info=True)
                        response_text = build_fallback_response()
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "manager_question":
                question = intent.parameters.get("question", incoming_text)
                if manager_gpt_service:
                    try:
                        response_text = await manager_gpt_service.answer_manager_question(question=question)
                    except Exception as e:
                        logger.error("Error calling Manager GPT service: %s", e, exc_info=True)
                        response_text = build_fallback_response()
                else:
                    response_text = build_fallback_response()
            
            elif intent.name == "llm_analysis":
                # Route to Gemini for analysis
                end_date = dt.date.today()
                start_date = dt.date(end_date.year - DEFAULT_METRICS_YEARS_BACK, 1, 1)
                metrics = supabase_service.get_metrics_summary(
                    start_date=start_date,
                    end_date=end_date,
                    max_rows=DEFAULT_MAX_ROWS_FOR_LLM,
                )
                
                if gemini_service:
                    try:
                        response_text = await gemini_service.answer_question(
                            question=incoming_text,
                            metrics=metrics,
                            knowledge_sections=combined_knowledge,
                            conversation_history=conversation_history,
                        )
                        # If knowledge sections were provided and used, mark as used
                        if combined_knowledge:
                            used_knowledge = True
                    except Exception as e:
                        logger.error("Error calling Gemini service: %s", e, exc_info=True)
                        response_text = build_fallback_response()
                else:
                    response_text = build_fallback_response()
            
            else:
                response_text = build_fallback_response()
    
        # Ensure we have a response
        if not response_text or not response_text.strip():
            response_text = build_fallback_response()
        
        logger.info("Chat response: %s", response_text[:200])
        
        # Collect citations from knowledge sections only if they were used
        citations = None
        if used_knowledge and knowledge_sections:
            citations = []
            for section in knowledge_sections:
                citations.append(
                    Citation(
                        document_title=section.get("document_title") or section.get("topic"),
                        source_file=section.get("source_file"),
                        excerpt=section.get("excerpt", ""),
                        section_id=section.get("section_id"),
                    )
                )
        
        return ChatResponse(answer=response_text, intent=intent_name, citations=citations)
    except HTTPException:
        # Re-raise HTTP exceptions (like 400 Bad Request)
        raise
    except Exception as e:
        # Catch any other unexpected errors
        logger.error("Unexpected error in chat_query: %s", e, exc_info=True)
        error_message = f"מצטער, אירעה שגיאה בעיבוד השאלה. אנא נסה שוב מאוחר יותר."
        return ChatResponse(answer=error_message, intent=None, citations=None)


@router.get("/recent-queries", response_model=RecentQueriesResponse)
async def get_recent_queries(
    supabase_service: SupabaseService = Depends(get_supabase_service),
) -> RecentQueriesResponse:
    """Get the 10 most recent queries from the database (always fetches fresh from DB)."""
    try:
        logger.info("Fetching recent queries from database...")
        queries = supabase_service.get_recent_queries(limit=10)
        logger.info("Retrieved %d queries from database", len(queries))
        
        # Convert to response model
        recent_queries = []
        for query in queries:
            recent_queries.append(
                RecentQuery(
                    id=query.get("id", 0),
                    user_text=query.get("user_text", ""),
                    response_text=query.get("response_text"),
                    intent=query.get("intent"),
                    created_at=str(query.get("created_at", "")),
                )
            )
        
        return RecentQueriesResponse(queries=recent_queries)
    except Exception as e:
        logger.error("Error getting recent queries: %s", e, exc_info=True)
        return RecentQueriesResponse(queries=[])

