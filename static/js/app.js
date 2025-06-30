/**
 * English Learning Player - Main Application
 * Modularized version with separated concerns
 */

// Import modules
import { AppState, getCurrentMedia, getSentences, setCurrentMedia, setSentences, addStateListener } from './modules/globals.js';
import { apiClient } from './modules/api-client.js';
import { uiManager } from './modules/ui-manager.js';

// Global variables for backward compatibility (will be gradually migrated to modules)
let currentMedia = null;
let sentences = [];
let audioPlayer = null;
let videoPlayer = null;
let currentPlayer = null;
let currentSentenceIndex = -1;
let currentSubtitleSentence = null;
let subtitleDisplayVisible = true;
let translationInterval = null;
let uploadedMediaId = null;

// DOM Ready initialization
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 English Learning Player - Modularized Version');
    
    // Initialize core elements
    audioPlayer = document.getElementById('audioPlayer');
    videoPlayer = document.getElementById('videoPlayer');
    
    // Setup event listeners
    setupEventListeners();
    
    // Initialize UI
    initializeUI();
    
    // Load initial data
    loadInitialData();
});

function setupEventListeners() {
    // Media player events
    if (videoPlayer) {
        videoPlayer.addEventListener('timeupdate', updateVideoSubtitles);
    }
    
    if (audioPlayer) {
        audioPlayer.addEventListener('timeupdate', updateAudioSubtitles);
    }
    
    // File input
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileUpload);
    }
    
    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearchInput);
    }
    
    // Keyboard controls
    document.addEventListener('keydown', handleKeyboardControls);
    
    // Setup drag and drop
    setupDragAndDrop();
}

function initializeUI() {
    // Initialize with media panel
    setTimeout(() => {
        uiManager.showPanel('media');
    }, 100);
    
    // Hide initial sections appropriately
    const uploadSection = document.getElementById('uploadSection');
    const processingOptions = document.getElementById('processingOptions');
    
    if (uploadSection) uploadSection.style.display = 'block';
    if (processingOptions) processingOptions.style.display = 'none';
}

async function loadInitialData() {
    try {
        // Load media list
        await loadMediaList();
    } catch (error) {
        console.error('Failed to load initial data:', error);
        uiManager.showMessage('초기 데이터 로드 실패', 'error');
    }
}

// Essential functions that need to remain in main app for now
// (These will be gradually moved to appropriate modules)

async function loadMediaList() {
    console.log('Loading media list...');
    try {
        const media = await apiClient.getMediaList();
        console.log('Media data:', media);
        
        const listEl = document.getElementById('mediaList');
        if (!listEl) {
            console.warn('Media list element not found');
            return;
        }

        if (media.length === 0) {
            listEl.innerHTML = '<div style="color: #858585; font-size: 0.9em; padding: 10px;">업로드된 미디어가 없습니다.</div>';
            return;
        }

        listEl.innerHTML = media.map(item => `
            <div class="media-item" onclick="selectMedia('${item.id}')" title="${item.originalFilename || item.filename}">
                <div style="font-weight: bold; margin-bottom: 3px;">${item.originalFilename || item.filename}</div>
                <div style="font-size: 0.8em; color: #858585;">
                    ${item.fileType} • ${formatFileSize(item.fileSize)} • ${formatDuration(item.duration)}
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading media list:', error);
        const listEl = document.getElementById('mediaList');
        if (listEl) {
            listEl.innerHTML = '<div style="color: #f44336; font-size: 0.9em; padding: 10px;">미디어 목록 로드 실패</div>';
        }
    }
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Temporary global functions for backward compatibility
window.loadMediaList = loadMediaList;
window.selectMedia = selectMedia;
window.handleFileUpload = handleFileUpload;
window.showUploadSection = showUploadSection;
window.generateSubtitles = generateSubtitles;

// Placeholder functions (to be implemented in modules)
function selectMedia(mediaId) {
    console.log('Selecting media:', mediaId);
    // TODO: Implement in media-player module
}

function handleFileUpload(event) {
    console.log('File upload:', event);
    // TODO: Implement in file-upload module
}

function showUploadSection() {
    const uploadSection = document.getElementById('uploadSection');
    if (uploadSection) {
        uploadSection.style.display = 'block';
        uploadSection.scrollIntoView({ behavior: 'smooth' });
    }
}

function generateSubtitles() {
    console.log('Generate subtitles called');
    // TODO: Implement in processing module
}

function setupDragAndDrop() {
    // TODO: Implement in file-upload module
}

function handleSearchInput() {
    // TODO: Implement in search module
}

function handleKeyboardControls() {
    // TODO: Implement in keyboard-controls module
}

function updateVideoSubtitles() {
    // TODO: Implement in subtitle-display module
}

function updateAudioSubtitles() {
    // TODO: Implement in subtitle-display module
}

console.log('✅ Main application initialized');