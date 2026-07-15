from flask import Flask, request, jsonify, render_template, send_file
import yt_dlp
import os
import json
import uuid
import time
import re

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# Use /tmp for Vercel
DOWNLOAD_FOLDER = '/tmp/downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

download_progress = {}

# Custom yt-dlp options for Vercel
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'extract_flat': False,
    'force_generic_extractor': False,
    'nocheckcertificate': True,
    'prefer_insecure': True,
}

def extract_video_id(url):
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([\w-]+)',
        r'(?:youtu\.be\/)([\w-]+)',
        r'(?:youtube\.com\/embed\/)([\w-]+)',
        r'(?:youtube\.com\/v\/)([\w-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Template error: {str(e)}"

@app.route('/api/info', methods=['POST'])
def get_info():
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Validate YouTube URL
        if not ('youtube.com' in url or 'youtu.be' in url):
            return jsonify({'error': 'Only YouTube URLs are supported'}), 400
        
        # Extract video ID
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        # Use direct video URL for better compatibility
        if 'youtu.be' in url:
            url = f"https://www.youtube.com/watch?v={video_id}"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'nocheckcertificate': True,
            'prefer_insecure': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return jsonify({'error': 'No information found'}), 400
            
            # Handle playlists
            if 'entries' in info:
                videos = []
                for entry in info['entries']:
                    if entry:
                        videos.append({
                            'title': entry.get('title', 'Unknown'),
                            'url': entry.get('webpage_url', entry.get('url', url)),
                            'id': entry.get('id', ''),
                            'duration': entry.get('duration', 0),
                            'thumbnail': entry.get('thumbnail', '')
                        })
                return jsonify({
                    'type': 'playlist',
                    'title': info.get('title', 'Playlist'),
                    'count': len(videos),
                    'videos': videos
                })
            else:
                formats = []
                for f in info.get('formats', []):
                    formats.append({
                        'format_id': f.get('format_id', ''),
                        'ext': f.get('ext', ''),
                        'resolution': f.get('resolution', f.get('height', 'unknown')),
                        'note': f.get('format_note', ''),
                        'filesize': f.get('filesize', 0),
                        'vcodec': f.get('vcodec', ''),
                        'acodec': f.get('acodec', '')
                    })
                
                return jsonify({
                    'type': 'video',
                    'title': info.get('title', 'Unknown'),
                    'id': info.get('id', ''),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': formats,
                    'url': info.get('webpage_url', url)
                })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    try:
        data = request.json
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best')
        audio_only = data.get('audio_only', False)
        subtitles = data.get('subtitles', False)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Validate YouTube URL
        if not ('youtube.com' in url or 'youtu.be' in url):
            return jsonify({'error': 'Only YouTube URLs are supported'}), 400
        
        task_id = str(uuid.uuid4())
        
        # Prepare download options with fallback
        if audio_only:
            format_string = 'bestaudio/best'
        else:
            format_string = f'{format_id}/best'
        
        ydl_opts = {
            'format': format_string,
            'outtmpl': f'/tmp/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'prefer_insecure': True,
            'extract_flat': False,
            'force_generic_extractor': False,
        }
        
        if audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        if subtitles:
            ydl_opts['writesubtitles'] = True
            ydl_opts['writeautomaticsub'] = True
            ydl_opts['embedsubs'] = True
            ydl_opts['subtitleslangs'] = ['en']
        
        download_progress[task_id] = {
            'status': 'downloading',
            'progress': 0,
            'filename': ''
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    download_progress[task_id] = {
                        'status': 'error',
                        'progress': 0,
                        'error': 'No info extracted'
                    }
                    return jsonify({'task_id': task_id, 'status': 'error'})
                
                # Get filename
                filename = ydl.prepare_filename(info)
                
                if audio_only:
                    base_name = filename.rsplit('.', 1)[0]
                    if os.path.exists(f'{base_name}.mp3'):
                        filename = f'{base_name}.mp3'
                
                # Check if file exists
                if os.path.exists(filename):
                    download_progress[task_id] = {
                        'status': 'completed',
                        'progress': 100,
                        'filename': os.path.basename(filename)
                    }
                else:
                    # Search for file
                    for f in os.listdir('/tmp'):
                        if f.startswith(os.path.basename(filename).rsplit('.', 1)[0]):
                            download_progress[task_id] = {
                                'status': 'completed',
                                'progress': 100,
                                'filename': f
                            }
                            break
                    else:
                        download_progress[task_id] = {
                            'status': 'error',
                            'progress': 0,
                            'error': 'File not found after download'
                        }
                        
        except yt_dlp.utils.DownloadError as e:
            if 'Video unavailable' in str(e):
                error_msg = 'Video is unavailable or private'
            else:
                error_msg = str(e)
            download_progress[task_id] = {
                'status': 'error',
                'progress': 0,
                'error': error_msg
            }
        except Exception as e:
            download_progress[task_id] = {
                'status': 'error',
                'progress': 0,
                'error': str(e)
            }
        
        return jsonify({
            'task_id': task_id,
            'status': 'started'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    progress = download_progress.get(task_id, {
        'status': 'not_found',
        'progress': 0
    })
    return jsonify(progress)

@app.route('/api/download/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            filepath = os.path.join('/tmp', filename)
        
        if os.path.exists(filepath):
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename
            )
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug')
def debug():
    import sys
    try:
        # Test yt-dlp
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        test_result = None
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                test_info = ydl.extract_info(test_url, download=False)
                test_result = "Success: " + test_info.get('title', 'No title')
        except Exception as e:
            test_result = "Error: " + str(e)
        
        return jsonify({
            'status': 'working',
            'python_version': sys.version,
            'yt_dlp_working': test_result,
            'download_folder': DOWNLOAD_FOLDER,
            'folder_exists': os.path.exists(DOWNLOAD_FOLDER),
            'is_writable': os.access(DOWNLOAD_FOLDER, os.W_OK),
            'template_exists': os.path.exists(os.path.join(app.template_folder, 'index.html'))
        })
    except Exception as e:
        return jsonify({'error': str(e)})

app = app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
