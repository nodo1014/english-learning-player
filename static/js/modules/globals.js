/**
 * Global State Management
 * Centralized state management for the English Learning Player
 */

export const AppState = {
    // Media state
    media: {
        current: null,
        sentences: [],
        uploadedId: null
    },
    
    // Player state
    players: {
        audio: null,
        video: null,
        current: null
    },
    
    // Subtitle state
    subtitles: {
        currentIndex: -1,
        currentSentence: null,
        visible: true
    },
    
    // Processing state
    processing: {
        translationInterval: null,
        status: {}
    },
    
    // UI state
    ui: {
        verbHighlightEnabled: false,
        verbModeEnabled: false,
        subtitleLanguage: 'english',
        overlaySize: 100,
        overlayPosition: 'bottom'
    }
};

// Getters
export const getCurrentMedia = () => AppState.media.current;
export const getSentences = () => AppState.media.sentences;
export const getCurrentPlayer = () => AppState.players.current;
export const getCurrentSentence = () => AppState.subtitles.currentSentence;
export const getCurrentSentenceIndex = () => AppState.subtitles.currentIndex;

// Setters
export const setCurrentMedia = (media) => { AppState.media.current = media; };
export const setSentences = (sentences) => { AppState.media.sentences = sentences; };
export const setCurrentPlayer = (player) => { AppState.players.current = player; };
export const setCurrentSentence = (sentence) => { AppState.subtitles.currentSentence = sentence; };
export const setCurrentSentenceIndex = (index) => { AppState.subtitles.currentIndex = index; };

// UI state helpers
export const isVerbHighlightEnabled = () => AppState.ui.verbHighlightEnabled;
export const toggleVerbHighlight = () => { AppState.ui.verbHighlightEnabled = !AppState.ui.verbHighlightEnabled; };
export const isVerbModeEnabled = () => AppState.ui.verbModeEnabled;
export const toggleVerbMode = () => { AppState.ui.verbModeEnabled = !AppState.ui.verbModeEnabled; };

// State change notifications (simple event system)
const stateListeners = [];

export const addStateListener = (callback) => {
    stateListeners.push(callback);
};

export const notifyStateChange = (type, data) => {
    stateListeners.forEach(listener => {
        try {
            listener(type, data);
        } catch (error) {
            console.error('State listener error:', error);
        }
    });
};