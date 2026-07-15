// Global variables
let currentUrl = '';
let currentTaskId = '';
let progressInterval = null;
let currentFilename = '';

// DOM Elements
const urlInput = document.getElementById('urlInput');
const fetchBtn = document.getElementById('fetchBtn');
const infoDiv = document.getElementById('info');
const thumbnail = document.getElementById('thumbnail');
const title = document.getElementById('title');
const details = document.getElementById('details');
const type = document.getElementById('type');
const formatSelect = document.getElementById('formatSelect');
const downloadBtn = document.getElementById('downloadBtn');
const progressDiv = document.getElementById('progress');
const progressFill = document.getElementById('progressFill');
const progressStatus = document.getElementById('progressStatus');
const errorDiv = document.getElementById('error');

/**
 * Fetch video information from API
 */
async function fetchInfo() {
    const url = urlInput.value.trim();
    
    if (!url) {
        showError('Please enter a YouTube URL');
        return;
    }
    
    currentUrl = url;
    hideError();
    hideProgress();
    
    // Show loading state
    setLoading(true);
    
    try {
        const response = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        displayVideoInfo(data);
        
    } catch (error) {
        showError('Failed to fetch video info: ' + error.message);
    } finally {
        setLoading(false);
    }
}

/**
 * Display video information
 */
function displayVideoInfo(data) {
    infoDiv.style.display = 'block';
    infoDiv.classList.add('fade-in');
    
    // Set video details
    title.textContent = data.title || 'Unknown Title';
    details.textContent = `Duration: ${formatDuration(data.duration)}`;
    type.textContent = `Type: ${data.type || 'Video'}`;
    
    // Set thumbnail
    if (data.thumbnail) {
        thumbnail.src = data.thumbnail;
        thumbnail.style.display = 'block';
    } else {
        thumbnail.style.display = 'none';
    }
    
    // Populate formats
    populateFormats(data.formats || []);
    
    // Enable download button
    downloadBtn.disabled = false;
}

/**
 * Populate format dropdown
 */
function populateFormats(formats) {
    // Keep default options
    formatSelect.innerHTML = `
        <option value="best">Best Quality</option>
        <option value="bestvideo+bestaudio/best">Best Video + Audio</option>
        <option value="bestvideo[height<=1080]+bestaudio/best">1080p</option>
        <option value="bestvideo[height<=720]+bestaudio/best">720p</option>
        <option value="bestvideo[height<=480]+bestaudio/best">480p</option>
        <option value="bestaudio">Best Audio Only</option>
    `;
    
    // Add format-specific options
    if (formats && formats.length > 0) {
        const uniqueFormats = new Map();
        formats.forEach(f => {
            const key = f.format_id;
            if (!uniqueFormats.has(key)) {
                uniqueFormats.set(key, f);
            }
        });
        
        uniqueFormats.forEach((f, id) => {
            if (id && id !== '0') {
                const label = `${id} - ${f.resolution || f.ext} ${f.note || ''}`.trim();
                formatSelect.innerHTML += `<option value="${id}">${label}</option>`;
            }
        });
    }
}

/**
 * Start download
 */
async function startDownload() {
    if (!currentUrl) {
        showError('Please fetch video info first');
        return;
    }
    
    const audioOnly = document.querySelector('input[name="downloadType"]:checked').value === 'audio';
    const subtitles = document.getElementById('subtitlesCheck').checked;
    const formatId = formatSelect.value;
    
    // Disable download button
    downloadBtn.textContent = '⏳ Downloading...';
    downloadBtn.disabled = true;
    
    showProgress('Starting download...');
    hideError();
    
    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentUrl,
                format_id: formatId,
                audio_only: audioOnly,
                subtitles: subtitles
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            downloadBtn.textContent = '⬇️ Download';
            downloadBtn.disabled = false;
            return;
        }
        
        currentTaskId = data.task_id;
        startProgressPolling();
        
    } catch (error) {
        showError('Failed to start download: ' + error.message);
        downloadBtn.textContent = '⬇️ Download';
        downloadBtn.disabled = false;
    }
}

/**
 * Poll for download progress
 */
function startProgressPolling() {
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    progressInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${currentTaskId}`);
            const data = await response.json();
            
            // Update progress
            progressFill.style.width = data.progress + '%';
            
            // Update status
            let statusText = '';
            if (data.status === 'downloading') {
                statusText = `Downloading... ${data.progress}%`;
            } else if (data.status === 'completed') {
                statusText = '✅ Download complete!';
                clearInterval(progressInterval);
                progressInterval = null;
                currentFilename = data.filename;
                
                // Show download link
                progressStatus.innerHTML = `
                    ✅ Download complete!
                    <br>
                    <a href="/api/download/${data.filename}" class="download-link">
                        📥 Download File
                    </a>
                `;
                
                downloadBtn.textContent = '✅ Done!';
                downloadBtn.disabled = false;
                return;
            } else if (data.status === 'error') {
                statusText = '❌ Error: ' + (data.error || 'Download failed');
                clearInterval(progressInterval);
                progressInterval = null;
                showError(data.error || 'Download failed');
                downloadBtn.textContent = '⬇️ Download';
                downloadBtn.disabled = false;
                return;
            } else {
                statusText = 'Waiting...';
            }
            
            progressStatus.textContent = statusText;
            
        } catch (error) {
            console.error('Progress polling error:', error);
        }
    }, 1000);
}

/**
 * Download file
 */
function downloadFile(filename) {
    if (filename) {
        window.location.href = `/api/download/${filename}`;
    } else if (currentFilename) {
        window.location.href = `/api/download/${currentFilename}`;
    }
}

/**
 * Show progress bar
 */
function showProgress(status) {
    progressDiv.style.display = 'block';
    progressStatus.textContent = status || 'Starting...';
    progressFill.style.width = '0%';
}

/**
 * Hide progress bar
 */
function hideProgress() {
    progressDiv.style.display = 'none';
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

/**
 * Show error message
 */
function showError(message) {
    errorDiv.textContent = '❌ ' + message;
    errorDiv.style.display = 'block';
    errorDiv.classList.add('shake');
    setTimeout(() => {
        errorDiv.classList.remove('shake');
    }, 500);
}

/**
 * Hide error message
 */
function hideError() {
    errorDiv.style.display = 'none';
}

/**
 * Set loading state
 */
function setLoading(loading) {
    if (loading) {
        fetchBtn.innerHTML = '<span class="spinner"></span> Loading...';
        fetchBtn.disabled = true;
    } else {
        fetchBtn.textContent = 'Fetch';
        fetchBtn.disabled = false;
    }
}

/**
 * Paste from clipboard
 */
function pasteFromClipboard() {
    navigator.clipboard.readText()
        .then(text => {
            urlInput.value = text;
            // Auto-fetch after paste
            setTimeout(fetchInfo, 300);
        })
        .catch(() => {
            // Fallback
            alert('Please paste the URL manually (Ctrl+V / Cmd+V)');
        });
}

/**
 * Clear input and reset UI
 */
function clearInput() {
    urlInput.value = '';
    infoDiv.style.display = 'none';
    hideProgress();
    hideError();
    downloadBtn.textContent = '⬇️ Download';
    downloadBtn.disabled = true;
    thumbnail.style.display = 'none';
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

/**
 * Format duration
 */
function formatDuration(seconds) {
    if (!seconds) return '--';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Enter key support
    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            fetchInfo();
        }
    });
    
    // Auto-detect URL paste
    urlInput.addEventListener('paste', function() {
        setTimeout(() => {
            if (urlInput.value.trim()) {
                // Auto-fetch after paste
                setTimeout(fetchInfo, 500);
            }
        }, 100);
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+Enter or Cmd+Enter to fetch
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (document.activeElement === urlInput) {
            fetchInfo();
        }
    }
    
    // Escape to clear
    if (e.key === 'Escape') {
        clearInput();
    }
});