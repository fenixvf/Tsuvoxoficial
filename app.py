import os
import sys
import uuid
import threading
import time
import json
import traceback
import zipfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max

UPLOAD_DIR = Path('temp/uploads')
OUTPUT_DIR = Path('temp/outputs')
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma', 'aiff'}
ALLOWED_MODELS = {'htdemucs', 'htdemucs_ft', 'htdemucs_6s', 'mdx_extra', 'mdx_extra_q'}
ALLOWED_STEMS = {'vocals', 'all', 'karaoke'}

# In-memory job store
jobs = {}
jobs_lock = threading.Lock()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_job(job_id, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)

def run_separation(job_id, input_path, model, stems):
    """Run Demucs separation in background thread."""
    try:
        update_job(job_id, status='processing', progress=10, message='Carregando modelo de IA...')

        import subprocess
        output_job_dir = OUTPUT_DIR / job_id
        output_job_dir.mkdir(parents=True, exist_ok=True)

        # Resolve to absolute paths — subprocess runs with cwd=/tmp,
        # so relative paths would point to /tmp/... and fail silently.
        input_path_abs = Path(input_path).resolve()
        output_job_dir_abs = output_job_dir.resolve()

        runner = str(Path(__file__).parent.resolve() / 'web_demucs_runner.py')
        cmd = [
            sys.executable, runner,
            '--out', str(output_job_dir_abs),
            '-n', model,
        ]

        if stems == 'vocals':
            cmd += ['--two-stems', 'vocals']
        elif stems == 'karaoke':
            cmd += ['--two-stems', 'vocals']

        cmd.append(str(input_path_abs))

        update_job(job_id, progress=20, message='Separando áudio (isso pode levar alguns minutos)...')

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/tmp'  # prevents local demucs/ folder from shadowing installed package
        )

        # Stream stdout and collect both streams
        log_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                log_lines.append(line)
                if 'Separating track' in line:
                    update_job(job_id, progress=40, message='Processando faixas...')
                elif '%' in line:
                    try:
                        pct = int(line.split('%')[0].split()[-1])
                        mapped = 40 + int(pct * 0.5)
                        update_job(job_id, progress=min(mapped, 90), message=f'Separando... {pct}%')
                    except Exception:
                        pass

        stderr_output = process.stderr.read()
        process.wait()

        if process.returncode != 0:
            all_output = '\n'.join(log_lines[-15:])
            if stderr_output:
                all_output = stderr_output[-2000:] + '\n' + all_output
            update_job(job_id, status='error', message=f'Erro na separação: {all_output.strip()}')
            return

        update_job(job_id, progress=92, message='Preparando arquivos para download...')

        # Find output files
        base_name = Path(input_path).stem
        model_out_dir = output_job_dir / model / base_name
        
        if not model_out_dir.exists():
            # Try to find the output directory
            for d in output_job_dir.rglob('*'):
                if d.is_dir() and base_name in d.name:
                    model_out_dir = d
                    break

        output_files = {}
        if model_out_dir.exists():
            for f in model_out_dir.iterdir():
                if f.suffix in ('.wav', '.mp3', '.flac'):
                    stem_name = f.stem  # e.g. "vocals", "no_vocals", "drums", etc.
                    output_files[stem_name] = str(f)
        
        if not output_files:
            # Scan recursively
            for f in output_job_dir.rglob('*.wav'):
                stem_name = f.stem
                output_files[stem_name] = str(f)

        if not output_files:
            update_job(job_id, status='error', message='Nenhuma faixa encontrada na saída. Verifique se o modelo foi baixado corretamente.')
            return

        # Create zip of all outputs
        zip_path = output_job_dir / f'{base_name}_separated.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for stem_name, fpath in output_files.items():
                zf.write(fpath, f'{base_name}_{stem_name}.wav')

        update_job(
            job_id,
            status='done',
            progress=100,
            message='Separação concluída!',
            output_files=output_files,
            zip_path=str(zip_path),
            base_name=base_name
        )

    except Exception as e:
        tb = traceback.format_exc()
        update_job(job_id, status='error', message=f'Erro inesperado: {str(e)}', traceback=tb)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/process', methods=['POST'])
def process_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'Arquivo inválido'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': f'Formato não suportado. Use: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    model = request.form.get('model', 'htdemucs')
    stems = request.form.get('stems', 'vocals')

    if model not in ALLOWED_MODELS:
        return jsonify({'error': f'Modelo inválido. Escolha um dos: {", ".join(ALLOWED_MODELS)}'}), 400
    if stems not in ALLOWED_STEMS:
        return jsonify({'error': f'Modo de separação inválido.'}), 400

    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    input_path = UPLOAD_DIR / f'{job_id}_{filename}'
    file.save(str(input_path))

    with jobs_lock:
        jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'progress': 0,
            'message': 'Na fila...',
            'filename': filename,
            'model': model,
            'stems': stems,
            'created_at': time.time()
        }

    thread = threading.Thread(target=run_separation, args=(job_id, input_path, model, stems), daemon=True)
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/api/status/<job_id>')
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job não encontrado'}), 404
    
    # Return safe subset
    result = {
        'id': job['id'],
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'filename': job.get('filename'),
    }
    if job['status'] == 'done':
        result['stems'] = list(job.get('output_files', {}).keys())
        result['base_name'] = job.get('base_name', '')
    if job['status'] == 'error':
        result['error_detail'] = job.get('message', '')
    return jsonify(result)


@app.route('/api/download/<job_id>/zip')
def download_zip(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job não disponível'}), 404
    zip_path = job.get('zip_path')
    if not zip_path or not Path(zip_path).exists():
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    return send_file(zip_path, as_attachment=True, download_name=f"{job['base_name']}_separado.zip")


@app.route('/api/download/<job_id>/<stem>')
def download_stem(job_id, stem):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job não disponível'}), 404
    output_files = job.get('output_files', {})
    if stem not in output_files:
        return jsonify({'error': 'Faixa não encontrada'}), 404
    fpath = output_files[stem]
    if not Path(fpath).exists():
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    base_name = job.get('base_name', 'audio')
    return send_file(fpath, as_attachment=True, download_name=f'{base_name}_{stem}.wav')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
