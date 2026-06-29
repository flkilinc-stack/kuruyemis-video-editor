from flask import Flask, request, jsonify, send_file
import subprocess
import urllib.request
import os
import uuid

app = Flask(__name__)

VIDEOS_DIR = '/tmp/edited_videos'
os.makedirs(VIDEOS_DIR, exist_ok=True)


def write_text_file(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/edit-video', methods=['POST'])
def edit_video():
    data = request.json or {}
    video_url = data.get('video_url')
    urun_adi  = data.get('urun_adi', 'KURUYEMIS').upper()
    hook      = data.get('hook', '')
    konum     = data.get('konum', '📍 NAZİLLİ/AYDIN  📞 0505 041 07 25')

    if not video_url:
        return jsonify({'error': 'video_url gerekli'}), 400

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
