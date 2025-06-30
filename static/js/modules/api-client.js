/**
 * API Client Module
 * Centralized API communication with error handling and retries
 */

class APIClient {
    constructor() {
        this.baseURL = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json'
        };
    }

    // Generic request method with error handling
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            ...options,
            headers: {
                ...this.defaultHeaders,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Handle different content types
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    }

    // GET request
    async get(endpoint, params = {}) {
        const url = new URL(endpoint, window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key] !== undefined && params[key] !== null) {
                url.searchParams.append(key, params[key]);
            }
        });
        
        return this.request(url.pathname + url.search, {
            method: 'GET'
        });
    }

    // POST request
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // PUT request
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    // DELETE request
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }

    // File upload with FormData
    async uploadFile(endpoint, formData) {
        return this.request(endpoint, {
            method: 'POST',
            headers: {}, // Let browser set content-type for FormData
            body: formData
        });
    }

    // Media API methods
    async getMediaList() {
        return this.get('/api/media');
    }

    async getMediaById(mediaId) {
        return this.get(`/api/media/${mediaId}`);
    }

    async getChapters(mediaId) {
        return this.get(`/api/media/${mediaId}/chapters`);
    }

    async getSentences(mediaId) {
        return this.get(`/api/media/${mediaId}/sentences`);
    }

    // Processing API methods
    async processWithWhisper(mediaId, options = {}) {
        return this.post(`/api/media/${mediaId}/process-whisper`, options);
    }

    async uploadSentences(mediaId, formData) {
        return this.uploadFile(`/api/media/${mediaId}/upload-sentences`, formData);
    }

    async getProcessingStatus(mediaId) {
        return this.get(`/api/media/${mediaId}/status`);
    }

    // Translation API methods
    async translateSentences(mediaId) {
        return this.post(`/api/media/${mediaId}/translate`);
    }

    async getTranslationStatus(mediaId) {
        return this.get(`/api/media/${mediaId}/translation-status`);
    }

    // Extraction API methods
    async extractSentenceMP3(mediaId, sentenceId) {
        return this.post(`/api/sentence/${mediaId}/${sentenceId}/extract-mp3`);
    }

    async extractSentenceMP4(mediaId, sentenceId, options = {}) {
        return this.post(`/api/sentence/${mediaId}/${sentenceId}/extract-mp4`, options);
    }

    async extractBookmarkedMP3(mediaId) {
        return this.post(`/api/media/${mediaId}/extract-bookmarked`);
    }

    async extractBookmarkedMP4(mediaId, options = {}) {
        return this.post(`/api/media/${mediaId}/extract-bookmarked-mp4`, options);
    }

    async extractAllSentencesMP4(mediaId, options = {}) {
        return this.post(`/api/media/${mediaId}/extract-all-sentences-mp4`, options);
    }

    // Bookmark API methods
    async toggleBookmark(mediaId, sentenceId) {
        return this.post(`/api/sentence/${mediaId}/${sentenceId}/toggle-bookmark`);
    }

    async getBookmarkedSentences(mediaId) {
        return this.get(`/api/media/${mediaId}/bookmarked`);
    }

    // Search API methods
    async searchSentences(query, mediaId = null) {
        const params = { query };
        if (mediaId) params.media_id = mediaId;
        return this.get('/api/search', params);
    }

    // Vocabulary API methods
    async analyzeVocabulary(mediaId) {
        return this.post(`/api/media/${mediaId}/analyze-vocabulary`);
    }

    async getWordDifficulty(words) {
        return this.post('/api/analyze-difficulty', { words });
    }

    // File serving methods
    async downloadFile(endpoint) {
        try {
            const response = await fetch(endpoint);
            if (!response.ok) {
                throw new Error(`Download failed: ${response.statusText}`);
            }
            return response;
        } catch (error) {
            console.error('Download error:', error);
            throw error;
        }
    }
}

// Create singleton instance
export const apiClient = new APIClient();
export default apiClient;