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

// Global functions for HTML onclick handlers
window.loadMediaList = loadMediaList;
window.selectMedia = selectMedia;
window.handleFileUpload = handleFileUpload;
window.showUploadSection = showUploadSection;
window.generateSubtitles = generateSubtitles;
window.playSentence = playSentence;
window.toggleBookmark = toggleBookmark;
window.extractSentenceMP3 = extractSentenceMP3;

// Media selection function
async function selectMedia(mediaId) {
    console.log('Selecting media:', mediaId);
    
    try {
        // Update current media
        currentMedia = mediaId;
        setCurrentMedia(mediaId);
        
        // Update UI to show selected media
        document.querySelectorAll('.media-item').forEach(item => {
            item.classList.remove('active');
        });
        event.target.closest('.media-item')?.classList.add('active');
        
        // Get media info and sentences
        const [media, sentencesData] = await Promise.all([
            apiClient.getMediaById(mediaId),
            apiClient.getSentences(mediaId)
        ]);
        
        sentences = sentencesData;
        setSentences(sentencesData);
        
        console.log('Media loaded:', media);
        console.log('Sentences loaded:', sentences.length);
        
        // Setup media player
        setupMediaPlayer(media);
        
        // Display sentences
        displaySentences(sentencesData);
        
        // Update UI sections
        const uploadSection = document.getElementById('uploadSection');
        const processingOptions = document.getElementById('processingOptions');
        
        if (sentencesData.length > 0) {
            if (uploadSection) uploadSection.style.display = 'none';
            if (processingOptions) processingOptions.style.display = 'none';
        } else {
            if (uploadSection) uploadSection.style.display = 'none';
            if (processingOptions) processingOptions.style.display = 'block';
        }
        
        uiManager.showMessage(`미디어 "${media.originalFilename || media.filename}" 로드 완료`, 'success');
        
    } catch (error) {
        console.error('Error selecting media:', error);
        uiManager.showMessage('미디어 로드 실패', 'error');
    }
}

function setupMediaPlayer(media) {
    const mediaPlayerDiv = document.getElementById('mediaPlayerDiv');
    
    if (!mediaPlayerDiv) return;
    
    mediaPlayerDiv.style.display = 'block';
    
    const mediaPath = `/uploads/${media.filename}`;
    
    if (media.fileType === 'video') {
        videoPlayer.src = mediaPath;
        videoPlayer.style.display = 'block';
        audioPlayer.style.display = 'none';
        currentPlayer = videoPlayer;
        
        setTimeout(() => uiManager.updateVideoSize(), 100);
    } else {
        audioPlayer.src = mediaPath;
        audioPlayer.style.display = 'block';
        videoPlayer.style.display = 'none';
        currentPlayer = audioPlayer;
    }
    
    console.log(`${media.fileType} player setup:`, mediaPath);
}

function displaySentences(sentences) {
    const sentencesDisplay = document.getElementById('sentencesDisplay');
    const sentenceList = document.getElementById('sentenceList');
    
    if (!sentences || sentences.length === 0) {
        if (sentencesDisplay) {
            sentencesDisplay.innerHTML = '<div style="text-align: center; color: #858585; padding: 20px;">문장이 없습니다. 자막을 생성해주세요.</div>';
        }
        if (sentenceList) {
            sentenceList.innerHTML = '<div style="color: #858585; padding: 10px;">문장이 없습니다.</div>';
        }
        return;
    }
    
    // Group by chapter/scene for main display
    const grouped = groupSentences(sentences);
    
    if (sentencesDisplay) {
        sentencesDisplay.innerHTML = renderGroupedSentences(grouped);
    }
    
    if (sentenceList) {
        sentenceList.innerHTML = sentences.map(s => `
            <div class="sentence-item" onclick="playSentence(${s.id})">
                <span class="sentence-number">${s.order}.</span>
                <div class="sentence-text">${s.english}</div>
                ${s.korean ? `<div class="sentence-korean">${s.korean}</div>` : ''}
            </div>
        `).join('');
    }
}

function groupSentences(sentences) {
    // Simple grouping by chapter/scene
    return sentences.reduce((acc, sentence) => {
        const chapter = sentence.chapterTitle || 'Chapter 1';
        const scene = sentence.sceneTitle || 'Scene 1';
        
        if (!acc[chapter]) acc[chapter] = {};
        if (!acc[chapter][scene]) acc[chapter][scene] = [];
        
        acc[chapter][scene].push(sentence);
        return acc;
    }, {});
}

function renderGroupedSentences(grouped) {
    return Object.entries(grouped).map(([chapterName, scenes]) => `
        <div class="chapter-section">
            <div class="chapter-header">
                <div class="chapter-title">${chapterName}</div>
            </div>
            <div class="chapter-content">
                ${Object.entries(scenes).map(([sceneName, sentences]) => `
                    <div class="scene-section">
                        <div class="scene-header">
                            <div class="scene-title">${sceneName}</div>
                        </div>
                        <div class="scene-content">
                            ${sentences.map(s => `
                                <div class="sentence-item" onclick="playSentence(${s.id})">
                                    <span class="sentence-number">${s.order}.</span>
                                    <div class="sentence-text">${s.english}</div>
                                    ${s.korean ? `<div class="sentence-korean">${s.korean}</div>` : ''}
                                    <button class="bookmark-btn" onclick="toggleBookmark(${s.id}, event)">⭐</button>
                                    <button class="extract-btn" onclick="extractSentenceMP3(${s.id}, event)">MP3</button>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

// Helper functions
function playSentence(sentenceId) {
    const sentence = sentences.find(s => s.id === sentenceId);
    if (sentence && currentPlayer) {
        currentPlayer.currentTime = sentence.startTime;
        currentPlayer.play();
        currentSentenceIndex = sentences.indexOf(sentence);
        currentSubtitleSentence = sentence;
        console.log('Playing sentence:', sentence.english);
    }
}

function toggleBookmark(sentenceId, event) {
    event.stopPropagation();
    console.log('Toggle bookmark:', sentenceId);
    // TODO: Implement bookmark API call
}

function extractSentenceMP3(sentenceId, event) {
    event.stopPropagation();
    console.log('Extract MP3:', sentenceId);
    // TODO: Implement MP3 extraction
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