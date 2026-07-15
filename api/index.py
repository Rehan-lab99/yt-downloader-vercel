from flask import Flask, request, jsonify, render_template, send_file
import yt_dlp
import os
import json
import uuid
import time

# Create Flask app with correct paths
app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# Use /tmp for Vercel (only writable directory)
DOWNLOAD_FOLDER = '/tmp/downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

download_progress = {}

@app.route('/')
def index():
    """Home page"""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Template error: {str(e)}"

@app.route('/api/info', methods=['POST'])
def get_info():
    """Get video information"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'ignoreerrors': True,
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
                # Single video
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
    """Start download"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best')
        audio_only = data.get('audio_only', False)
        subtitles = data.get('subtitles', False)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        task_id = str(uuid.uuid4())
        
        # Prepare download options
        ydl_opts = {
            'format': format_id if not audio_only else 'bestaudio/best',
            'outtmpl': f'/tmp/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'concurrent_fragments': 10,
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
        
        # Start download
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info:
                    # Get filename
                    filename = ydl.prepare_filename(info)
                    
                    # If audio only, check for mp3
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
                        # Try to find file
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
                else:
                    download_progress[task_id] = {
                        'status': 'error',
                        'progress': 0,
                        'error': 'No info extracted'
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
    """Get download progress"""
    progress = download_progress.get(task_id, {
        'status': 'not_found',
        'progress': 0
    })
    return jsonify(progress)

@app.route('/api/download/<filename>')
def download_file(filename):
    """Download the completed file"""
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            # Try /tmp directly
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
    """Debug endpoint"""
    import sys
    try:
        return jsonify({
            'status': 'working',
            'python_version': sys.version,
            'download_folder': DOWNLOAD_FOLDER,
            'folder_exists': os.path.exists(DOWNLOAD_FOLDER),
            'is_writable': os.access(DOWNLOAD_FOLDER, os.W_OK),
            'template_folder': app.template_folder,
            'static_folder': app.static_folder,
            'templates_exist': os.path.exists(app.template_folder),
            'index_exists': os.path.exists(os.path.join(app.template_folder, 'index.html'))
        })
    except Exception as e:
        return jsonify({'error': str(e)})

# This is what Vercel looks for
app = app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)