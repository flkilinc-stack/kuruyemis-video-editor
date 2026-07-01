from flask import Flask, request, jsonify, send_file
import subprocess
import urllib.request
import os
import uuid
import json

app = Flask(__name__)

VIDEOS_DIR = '/tmp/edited_videos'
os.makedirs(VIDEOS_DIR, exist_ok=True)

_drive_service = None


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        sa_info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        _drive_service = build('drive', 'v3', credentials=creds)
    return _drive_service


def download_drive_file(file_id, dest_path):
    from googleapiclient.http import MediaIoBaseDownload
    service = get_drive_service()
    req = service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def write_text_file(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/debug-drive')
def debug_drive():
    from google.oauth2 import service_account
    result = {}
    try:
        sa_info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
        result['service_account_email'] = sa_info.get('client_email')
    except Exception as e:
        return jsonify({'error': f'could not read GOOGLE_SERVICE_ACCOUNT_JSON: {e}'}), 500

    service = get_drive_service()
    for label, fid in [
        ('top_folder', '1PmjZtYYlMFUNS6Zx8hohEV3z6_L4Vbg7'),
        ('sub_folder', '1EB16caPpsCwPBCROgUsjyLCMO7kSpkia'),
        ('video_file', '1ExhChHa11MTpBfhUY0NpbNbrBpt2ylu5'),
    ]:
        try:
            meta = service.files().get(fileId=fid, fields='id,name,mimeType,owners,shared', supportsAllDrives=True).execute()
            result[label] = meta
        except Exception as e:
            result[label] = {'error': str(e)}

    try:
        listing = service.files().list(
            q="'1EB16caPpsCwPBCROgUsjyLCMO7kSpkia' in parents and trashed=false",
            fields='files(id,name,mimeType)',
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()
        result['list_sub_folder_children'] = listing
    except Exception as e:
        result['list_sub_folder_children'] = {'error': str(e)}

    return jsonify(result)


@app.route('/edit-video', methods=['POST'])
def edit_video():
    video_file = request.files.get('video')
    data = request.get_json(silent=True) or request.form

    file_id   = data.get('file_id') if not video_file else None
    video_url = data.get('video_url') if not video_file and not file_id else None
    urun_adi  = data.get('urun_adi', 'KURUYEMIS').upper()
    hook      = data.get('hook', '')
    konum     = data.get('konum', '📍 NAZİLLİ/AYDIN  📞 0505 041 07 25')

    if not video_file and not video_url and not file_id:
        return jsonify({'error': 'video dosyasi, file_id veya video_url gerekli'}), 400

    job_id      = str(uuid.uuid4())
    input_path  = f'/tmp/{job_id}_in.mp4'
    output_path = f'{VIDEOS_DIR}/{job_id}.mp4'
    title_file  = f'/tmp/{job_id}_title.txt'
    hook_file   = f'/tmp/{job_id}_hook.txt'
    konum_file  = f'/tmp/{job_id}_konum.txt'

    write_text_file(title_file, urun_adi)
    write_text_file(hook_file,  hook)
    write_text_file(konum_file, konum)

    try:
        if video_file:
            video_file.save(input_path)
        elif file_id:
            download_drive_file(file_id, input_path)
        else:
            req = urllib.request.Request(video_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as resp, open(input_path, 'wb') as f:
                f.write(resp.read())

        font_bold    = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
        font_regular = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

        vf = (
            "drawbox=x=0:y=0:w=iw:h=130:color=black@0.65:t=fill,"
            f"drawtext=fontfile='{font_bold}':textfile='{title_file}':"
            "fontsize=58:fontcolor=white:x=(w-text_w)/2:y=35:"
            "shadowcolor=black:shadowx=3:shadowy=3,"
            "drawbox=x=0:y=ih-220:w=iw:h=220:color=black@0.65:t=fill,"
            f"drawtext=fontfile='{font_bold}':textfile='{hook_file}':"
            "fontsize=34:fontcolor=white:x=(w-text_w)/2:y=h-195:"
            "shadowcolor=black:shadowx=2:shadowy=2,"
            f"drawtext=fontfile='{font_regular}':textfile='{konum_file}':"
            "fontsize=26:fontcolor=yellow:x=(w-text_w)/2:y=h-120:"
            "shadowcolor=black:shadowx=2:shadowy=2"
        )

        cmd = [
            'ffmpeg', '-i', input_path,
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'copy',
            '-y', output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if result.returncode != 0:
            return jsonify({'error': 'FFmpeg hatasi', 'details': result.stderr[-1000:]}), 500

        host = request.host_url.rstrip('/')
        return jsonify({
            'status': 'success',
            'video_url': f'{host}/video/{job_id}.mp4'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        for p in [input_path, title_file, hook_file, konum_file]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass


@app.route('/video/<filename>')
def serve_video(filename):
    if '..' in filename or '/' in filename:
        return jsonify({'error': 'Gecersiz dosya adi'}), 400
    path = os.path.join(VIDEOS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'Video bulunamadi'}), 404
    return send_file(path, mimetype='video/mp4')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
