/**
 * UI Manager Module
 * Handles UI state, panel management, and layout controls
 */

import { AppState, notifyStateChange } from './globals.js';

class UIManager {
    constructor() {
        this.leftSidebarCollapsed = false;
        this.rightSidebarCollapsed = false;
        this.currentPanel = 'media';
        
        this.initializeElements();
        this.setupEventListeners();
    }

    initializeElements() {
        this.leftSidebar = document.getElementById('leftSidebar');
        this.rightSidebar = document.getElementById('rightSidebar');
        this.sidebarHeader = document.getElementById('sidebarHeader');
        this.mainContent = document.querySelector('.main-content');
        this.videoPlayer = document.getElementById('videoPlayer');
    }

    setupEventListeners() {
        // Sidebar resize functionality
        this.initSidebarResize();
        
        // Window resize handler
        window.addEventListener('resize', () => this.updateVideoSize());
        
        // Panel switching
        document.querySelectorAll('.activity-item').forEach(button => {
            button.addEventListener('click', (e) => {
                const panel = this.getPanelFromButton(e.target);
                if (panel) this.showPanel(panel);
            });
        });
    }

    getPanelFromButton(button) {
        const panels = ['media', 'subtitle', 'analysis', 'mp3extract', 'mp4extract'];
        const buttons = document.querySelectorAll('.activity-item');
        const index = Array.from(buttons).indexOf(button);
        return panels[index] || null;
    }

    showPanel(panelType) {
        // Remove active class from all activity items
        document.querySelectorAll('.activity-item').forEach(item => {
            item.classList.remove('active');
        });

        // Add active class to clicked button
        const buttons = document.querySelectorAll('.activity-item');
        const panelIndex = ['media', 'subtitle', 'analysis', 'mp3extract', 'mp4extract'].indexOf(panelType);
        if (panelIndex >= 0 && buttons[panelIndex]) {
            buttons[panelIndex].classList.add('active');
        }

        // Hide all panels
        const panels = ['mediaPanel', 'subtitlePanel', 'analysisPanel', 'mp3extractPanel', 'mp4extractPanel'];
        panels.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (panel) panel.style.display = 'none';
        });

        // Show selected panel and update header
        this.displayPanel(panelType);
        this.currentPanel = panelType;
        
        // Notify state change
        notifyStateChange('panel-changed', panelType);
    }

    displayPanel(panelType) {
        const headerEl = this.sidebarHeader;
        
        switch(panelType) {
            case 'media':
                this.showPanelElement('mediaPanel', '미디어 파일');
                // Load media list when switching to media panel
                if (window.loadMediaList) window.loadMediaList();
                break;
            case 'subtitle':
                this.showPanelElement('subtitlePanel', '자막 생성');
                break;
            case 'analysis':
                this.showPanelElement('analysisPanel', '분석');
                break;
            case 'mp3extract':
                this.showPanelElement('mp3extractPanel', 'MP3 추출');
                break;
            case 'mp4extract':
                this.showPanelElement('mp4extractPanel', 'MP4 추출');
                break;
        }
    }

    showPanelElement(panelId, title) {
        const panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'block';
        
        if (this.sidebarHeader) {
            this.sidebarHeader.innerHTML = `
                <span>${title}</span>
                <button class="sidebar-toggle" onclick="uiManager.toggleLeftSidebar()" title="사이드바 숨김/보이기">×</button>
            `;
        }
    }

    toggleLeftSidebar() {
        if (!this.leftSidebar) return;

        this.leftSidebarCollapsed = !this.leftSidebarCollapsed;
        
        if (this.leftSidebarCollapsed) {
            this.leftSidebar.classList.add('collapsed');
        } else {
            this.leftSidebar.classList.remove('collapsed');
        }

        // Update video size after sidebar toggle
        setTimeout(() => this.updateVideoSize(), 300);
        
        notifyStateChange('sidebar-toggled', { side: 'left', collapsed: this.leftSidebarCollapsed });
    }

    toggleRightSidebar() {
        if (!this.rightSidebar) return;

        this.rightSidebarCollapsed = !this.rightSidebarCollapsed;
        
        if (this.rightSidebarCollapsed) {
            this.rightSidebar.classList.add('collapsed');
        } else {
            this.rightSidebar.classList.remove('collapsed');
        }

        // Update video size after sidebar toggle
        setTimeout(() => this.updateVideoSize(), 300);
        
        notifyStateChange('sidebar-toggled', { side: 'right', collapsed: this.rightSidebarCollapsed });
    }

    updateVideoSize() {
        if (!this.videoPlayer) return;

        // Responsive video sizing based on container
        const container = this.videoPlayer.parentElement;
        if (container) {
            const containerWidth = container.clientWidth;
            const containerHeight = container.clientHeight;
            
            // Maintain aspect ratio while fitting container
            this.videoPlayer.style.maxWidth = `${containerWidth}px`;
            this.videoPlayer.style.maxHeight = `${Math.min(containerHeight * 0.7, containerWidth * 0.5625)}px`;
        }
    }

    initSidebarResize() {
        // Left sidebar resize
        const leftResizer = document.getElementById('leftSidebarResizer');
        if (leftResizer) {
            this.makeResizable(leftResizer, this.leftSidebar, 'width', 200, 600);
        }

        // Right sidebar resize
        const rightResizer = document.getElementById('rightSidebarResizer');
        if (rightResizer) {
            this.makeResizable(rightResizer, this.rightSidebar, 'width', 300, 800);
        }
    }

    makeResizable(resizer, element, property, min, max) {
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startWidth = parseInt(window.getComputedStyle(element).width, 10);
            document.body.style.cursor = 'ew-resize';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const width = startWidth + (e.clientX - startX);
            const clampedWidth = Math.min(Math.max(width, min), max);
            
            element.style.width = `${clampedWidth}px`;
            this.updateVideoSize();
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
            }
        });
    }

    showMessage(message, type = 'info', duration = 3000) {
        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = `message message-${type}`;
        messageEl.textContent = message;
        messageEl.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 15px;
            border-radius: 5px;
            z-index: 10000;
            opacity: 0;
            transition: opacity 0.3s ease;
            max-width: 300px;
            word-wrap: break-word;
        `;

        // Set type-specific styles
        switch (type) {
            case 'success':
                messageEl.style.background = '#4CAF50';
                messageEl.style.color = 'white';
                break;
            case 'error':
                messageEl.style.background = '#f44336';
                messageEl.style.color = 'white';
                break;
            case 'warning':
                messageEl.style.background = '#ff9800';
                messageEl.style.color = 'white';
                break;
            default:
                messageEl.style.background = '#2196F3';
                messageEl.style.color = 'white';
        }

        document.body.appendChild(messageEl);
        
        // Fade in
        setTimeout(() => messageEl.style.opacity = '1', 10);
        
        // Auto remove
        setTimeout(() => {
            messageEl.style.opacity = '0';
            setTimeout(() => {
                if (messageEl.parentNode) {
                    messageEl.parentNode.removeChild(messageEl);
                }
            }, 300);
        }, duration);
    }

    showVolumeIndicator(volume) {
        const indicator = document.createElement('div');
        indicator.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 1.2em;
            z-index: 10000;
            pointer-events: none;
        `;
        indicator.textContent = `🔊 ${Math.round(volume * 100)}%`;
        
        document.body.appendChild(indicator);
        
        setTimeout(() => {
            if (indicator.parentNode) {
                indicator.parentNode.removeChild(indicator);
            }
        }, 1000);
    }

    getCurrentPanel() {
        return this.currentPanel;
    }

    isLeftSidebarCollapsed() {
        return this.leftSidebarCollapsed;
    }

    isRightSidebarCollapsed() {
        return this.rightSidebarCollapsed;
    }
}

// Create singleton instance
export const uiManager = new UIManager();

// Make globally available for backward compatibility
window.uiManager = uiManager;
window.showPanel = (panelType) => uiManager.showPanel(panelType);
window.toggleLeftSidebar = () => uiManager.toggleLeftSidebar();
window.toggleRightSidebar = () => uiManager.toggleRightSidebar();

export default uiManager;