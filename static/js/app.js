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

// Folder import functionality - make sure it's global
window.switchUploadMethod = function(method) {
    const singleFileBtn = document.getElementById('singleFileBtn');
    const folderOpenBtn = document.getElementById('folderOpenBtn');
    const singleFileUpload = document.getElementById('singleFileUpload');
    const folderImport = document.getElementById('folderImport');
    
    if (method === 'single') {
        singleFileBtn.style.background = '#007acc';
        folderOpenBtn.style.background = '#404040';
        singleFileUpload.style.display = 'block';
        folderImport.style.display = 'none';
    } else {
        singleFileBtn.style.background = '#404040';
        folderOpenBtn.style.background = '#007acc';
        singleFileUpload.style.display = 'none';
        folderImport.style.display = 'block';
    }
}

async function loadSyncDirectory() {
    try {
        const loadBtn = document.getElementById('loadSyncFolderBtn');
        loadBtn.disabled = true;
        loadBtn.textContent = '로딩 중...';
        
        const response = await fetch('/api/sync-directory');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load sync directory');
        }
        
        displaySyncFiles(data.files);
        document.getElementById('syncFileList').style.display = 'block';
        
    } catch (error) {
        console.error('Error loading sync directory:', error);
        alert('폴더를 불러오는 중 오류가 발생했습니다: ' + error.message);
    } finally {
        const loadBtn = document.getElementById('loadSyncFolderBtn');
        loadBtn.disabled = false;
        loadBtn.textContent = '📂 sync_directory 새로고침';
    }
}

// Make function globally available
window.loadSyncDirectory = loadSyncDirectory;

// Store selected files globally
let selectedFiles = new Set();

function displaySyncFiles(files) {
    const fileList = document.getElementById('fileClickList');
    fileList.innerHTML = '';
    selectedFiles.clear();
    updateSelectedCount();
    
    if (files.length === 0) {
        fileList.innerHTML = '<div style="color: #858585; text-align: center; padding: 20px;">sync_directory 폴더에 미디어 파일이 없습니다.</div>';
        return;
    }
    
    files.forEach(fileGroup => {
        const fileItem = document.createElement('div');
        fileItem.style.cssText = 'margin-bottom: 8px; padding: 12px; background: #2d2d30; border-radius: 4px; border: 2px solid #404040; cursor: pointer; transition: all 0.2s;';
        fileItem.dataset.baseName = fileGroup.baseName;
        
        // Click event for selection
        fileItem.addEventListener('click', function() {
            toggleFileSelection(this, fileGroup.baseName);
        });
        
        // Hover effect
        fileItem.addEventListener('mouseenter', function() {
            if (!this.classList.contains('selected')) {
                this.style.borderColor = '#007acc';
                this.style.background = '#3d3d40';
            }
        });
        
        fileItem.addEventListener('mouseleave', function() {
            if (!this.classList.contains('selected')) {
                this.style.borderColor = '#404040';
                this.style.background = '#2d2d30';
            }
        });
        
        let labelText = `📁 ${fileGroup.baseName}`;
        let details = [];
        
        if (fileGroup.mediaFile) {
            const sizeText = formatFileSize(fileGroup.mediaFile.size);
            details.push(`🎬 ${fileGroup.mediaFile.extension} (${sizeText})`);
        }
        
        if (fileGroup.subtitleFile) {
            details.push(`📄 자막 파일`);
        }
        
        if (details.length > 0) {
            labelText += ` - ${details.join(', ')}`;
        }
        
        fileItem.innerHTML = `
            <div style="display: flex; align-items: center; color: #cccccc;">
                <span style="margin-right: 8px;">☐</span>
                <span>${labelText}</span>
            </div>
        `;
        
        fileList.appendChild(fileItem);
    });
}

function toggleFileSelection(element, baseName) {
    const checkbox = element.querySelector('span');
    
    if (selectedFiles.has(baseName)) {
        // Deselect
        selectedFiles.delete(baseName);
        element.classList.remove('selected');
        element.style.borderColor = '#404040';
        element.style.background = '#2d2d30';
        checkbox.textContent = '☐';
    } else {
        // Select
        selectedFiles.add(baseName);
        element.classList.add('selected');
        element.style.borderColor = '#28a745';
        element.style.background = '#1a3d1a';
        checkbox.textContent = '☑';
    }
    
    updateSelectedCount();
}

function updateSelectedCount() {
    const countSpan = document.getElementById('selectedCount');
    const importBtn = document.getElementById('importSelectedBtn');
    
    countSpan.textContent = selectedFiles.size;
    importBtn.disabled = selectedFiles.size === 0;
    
    if (selectedFiles.size === 0) {
        importBtn.style.background = '#666666';
    } else {
        importBtn.style.background = '#28a745';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function selectAllFiles() {
    const fileItems = document.querySelectorAll('#fileClickList div[data-base-name]');
    fileItems.forEach(item => {
        const baseName = item.dataset.baseName;
        if (!selectedFiles.has(baseName)) {
            toggleFileSelection(item, baseName);
        }
    });
}

function deselectAllFiles() {
    const fileItems = document.querySelectorAll('#fileClickList div[data-base-name]');
    fileItems.forEach(item => {
        const baseName = item.dataset.baseName;
        if (selectedFiles.has(baseName)) {
            toggleFileSelection(item, baseName);
        }
    });
}

// Make functions globally available
window.selectAllFiles = selectAllFiles;
window.deselectAllFiles = deselectAllFiles;

async function importSelectedFiles() {
    const selectedFilesArray = Array.from(selectedFiles);
    
    if (selectedFilesArray.length === 0) {
        alert('가져올 파일을 선택해주세요.');
        return;
    }
    
    try {
        const importBtn = document.getElementById('importSelectedBtn');
        importBtn.disabled = true;
        importBtn.textContent = '가져오는 중...';
        
        document.getElementById('importProgress').style.display = 'block';
        updateImportProgress(0, '파일 가져오기 시작...');
        
        const response = await fetch('/api/sync-directory/import', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                selectedFiles: selectedFilesArray
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Import failed');
        }
        
        // Process results
        const successCount = data.results.filter(r => r.success).length;
        const totalCount = data.results.length;
        
        updateImportProgress(100, `완료: ${successCount}/${totalCount} 파일 가져오기 성공`);
        
        // Show detailed results
        let message = `파일 가져오기 완료!\n성공: ${successCount}개\n실패: ${totalCount - successCount}개`;
        
        const failedFiles = data.results.filter(r => !r.success);
        if (failedFiles.length > 0) {
            message += '\n\n실패한 파일:';
            failedFiles.forEach(file => {
                message += `\n- ${file.baseName}: ${file.error}`;
            });
        }
        
        alert(message);
        
        // Refresh the file list
        if (successCount > 0) {
            loadSyncDirectory();
            // Refresh media list if it's visible
            if (typeof loadMedia === 'function') {
                loadMedia();
            }
        }
        
    } catch (error) {
        console.error('Error importing files:', error);
        alert('파일 가져오기 중 오류가 발생했습니다: ' + error.message);
        updateImportProgress(0, '오류 발생');
    } finally {
        const importBtn = document.getElementById('importSelectedBtn');
        importBtn.disabled = false;
        importBtn.textContent = '선택한 파일 가져오기';
        
        setTimeout(() => {
            document.getElementById('importProgress').style.display = 'none';
        }, 3000);
    }
}

// Make function globally available
window.importSelectedFiles = importSelectedFiles;

function updateImportProgress(percentage, status) {
    const progressFill = document.getElementById('importProgressFill');
    const statusDiv = document.getElementById('importStatus');
    
    progressFill.style.width = percentage + '%';
    statusDiv.textContent = status || '';
}

// Auto-load sync directory on page load - handled in HTML

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