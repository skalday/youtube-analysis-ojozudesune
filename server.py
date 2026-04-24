from flask import Flask, request, jsonify, send_from_directory, Response
from pathlib import Path
import os
import json
import shutil
from dotenv import load_dotenv
import queue
import threading

load_dotenv()

from config.settings import load_settings
from modules.fetcher import YouTubeFetcher
from modules.analyzer import ChannelAnalyzer
from modules.llm_providers.local_llm import LocalLLMClient

app = Flask(__name__, static_folder='.')

message_queues = {}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        channel = data.get('channel')
        local_model = data.get('localModel')
        max_videos = data.get('maxVideos', 20)
        skip_audience = data.get('skipAudience', False)
        skip_brand = data.get('skipBrand', False)
        if not channel:
            return jsonify({'error': '缺少頻道參數'}), 400

        task_id = str(hash(channel + str(os.urandom(8))))
        msg_queue = queue.Queue()
        message_queues[task_id] = msg_queue

        def run_analysis():
            try:
                msg_queue.put('開始分析...')

                settings = load_settings()
                settings.max_videos = max_videos

                msg_queue.put('正在抓取頻道資料...')
                fetcher = YouTubeFetcher(settings)
                channel_id, channel_title, videos, transcripts, comments, fetch_time = fetcher.fetch(channel)
                msg_queue.put(f'已抓取 {len(videos)} 支影片')

                llm = LocalLLMClient(model=local_model) if local_model else LocalLLMClient()
                msg_queue.put(f'初始化 Ollama 模型{f" ({local_model})" if local_model else ""}...')

                out_dir = Path(settings.reports_dir) / channel_id
                analyzer = ChannelAnalyzer(llm=llm, data_dir=settings.data_dir, out_dir=out_dir)

                msg_queue.put('開始 LLM 分析...')
                analyzer.analyze(
                    channel_id=channel_id,
                    channel_title=channel_title,
                    videos=videos,
                    transcripts=transcripts,
                    all_comments=comments,
                    skip_audience=skip_audience,
                    skip_brand=skip_brand,
                    max_videos=max_videos,
                    last_fetched=fetch_time,
                )

                msg_queue.put('讀取分析結果...')
                summary_path = out_dir / 'summary.json'
                summary = json.loads(summary_path.read_text(encoding='utf-8'))

                msg_queue.put('DONE:' + json.dumps({
                    'success': True,
                    'summary': summary,
                }))

            except Exception as e:
                import traceback
                msg_queue.put('ERROR:' + str(e) + '\n' + traceback.format_exc())

        thread = threading.Thread(target=run_analysis)
        thread.start()

        return jsonify({'task_id': task_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream/<task_id>')
def stream(task_id):
    def event_stream():
        msg_queue = message_queues.get(task_id)
        if not msg_queue:
            yield 'data: {"error": "Task not found"}\n\n'
            return

        while True:
            msg = msg_queue.get()
            yield f'data: {json.dumps({"message": msg})}\n\n'

            if msg.startswith('DONE:') or msg.startswith('ERROR:'):
                del message_queues[task_id]
                break

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/api/list_cached_channels', methods=['GET'])
def list_cached_channels():
    try:
        settings = load_settings()
        reports_dir = Path(settings.reports_dir)

        if not reports_dir.exists():
            return jsonify({'channels': []})

        channels = []
        for channel_dir in reports_dir.iterdir():
            if channel_dir.is_dir():
                summary_path = channel_dir / 'summary.json'
                if summary_path.exists():
                    try:
                        summary = json.loads(summary_path.read_text(encoding='utf-8'))
                        channels.append({
                            'channel_id': channel_dir.name,
                            'channel_title': summary.get('channel_title', channel_dir.name),
                            'last_updated': summary.get('last_updated', 'Unknown'),
                            'last_fetched': summary.get('last_fetched', 'Unknown'),
                            'total_videos': summary.get('stats', {}).get('total_videos', 0)
                        })
                    except:
                        continue

        channels.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
        return jsonify({'channels': channels})

    except Exception as e:
        return jsonify({'error': str(e), 'channels': []}), 500

@app.route('/api/load_cache', methods=['POST'])
def load_cache():
    try:
        data = request.json
        channel_id = data.get('channel_id')

        if not channel_id:
            return jsonify({'error': '缺少 channel_id 參數'}), 400

        settings = load_settings()
        out_dir = Path(settings.reports_dir) / channel_id

        if not out_dir.exists():
            return jsonify({'error': f'找不到頻道 {channel_id} 的快取資料'}), 404

        summary_path = out_dir / 'summary.json'
        if not summary_path.exists():
            return jsonify({'error': f'頻道 {channel_id} 缺少 summary.json'}), 404

        summary = json.loads(summary_path.read_text(encoding='utf-8'))

        return jsonify({'success': True, 'summary': summary})

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

def _make_task(fn):
    """Run fn in background, return task_id for SSE streaming."""
    task_id = str(hash(os.urandom(8)))
    msg_queue = queue.Queue()
    message_queues[task_id] = msg_queue
    threading.Thread(target=fn, args=(msg_queue,)).start()
    return jsonify({'task_id': task_id})

def _llm_from_request(data):
    local_model = data.get('localModel')
    return LocalLLMClient(model=local_model) if local_model else LocalLLMClient()

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
def delete_channel(channel_id):
    try:
        settings = load_settings()
        reports_dir = Path(settings.reports_dir) / channel_id
        data_dir = Path(settings.data_dir)

        if reports_dir.exists():
            shutil.rmtree(reports_dir)
        for sub in ('videos', 'transcripts', 'comments'):
            p = data_dir / 'raw' / sub / channel_id
            if p.exists():
                shutil.rmtree(p)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<channel_id>/fetch_and_analyze', methods=['POST'])
def fetch_and_analyze(channel_id):
    data = request.json or {}
    llm = _llm_from_request(data)

    def run(msg_queue):
        try:
            settings = load_settings()
            out_dir = Path(settings.reports_dir) / channel_id
            summary_path = out_dir / 'summary.json'
            if not summary_path.exists():
                msg_queue.put('ERROR:找不到 summary.json，請先執行完整分析')
                return

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            channel_title = summary.get('channel_title', channel_id)
            last_fetched = summary.get('last_fetched', summary.get('last_updated'))

            msg_queue.put(f'補抓 {last_fetched[:10]} 之後的新影片...')
            fetcher = YouTubeFetcher(settings)
            channel_id_, channel_title_, videos, transcripts, comments, fetch_time = \
                fetcher.fetch_incremental(channel_id, channel_title, last_fetched)
            msg_queue.put(f'共 {len(videos)} 支影片，開始分析...')

            analyzer = ChannelAnalyzer(llm=llm, data_dir=settings.data_dir, out_dir=out_dir)
            analyzer.analyze(
                channel_id=channel_id, channel_title=channel_title,
                videos=videos, transcripts=transcripts, all_comments=comments,
                last_fetched=fetch_time,
            )

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            msg_queue.put('DONE:' + json.dumps({'success': True, 'summary': summary}))
        except Exception as e:
            import traceback
            msg_queue.put('ERROR:' + str(e) + '\n' + traceback.format_exc())

    return _make_task(run)

@app.route('/api/channels/<channel_id>/analyze', methods=['POST'])
def analyze_cached(channel_id):
    data = request.json or {}
    llm = _llm_from_request(data)

    def run(msg_queue):
        try:
            settings = load_settings()
            out_dir = Path(settings.reports_dir) / channel_id
            summary_path = out_dir / 'summary.json'
            if not summary_path.exists():
                msg_queue.put('ERROR:找不到 summary.json，請先執行完整分析')
                return

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            channel_title = summary.get('channel_title', channel_id)
            last_fetched = summary.get('last_fetched')

            msg_queue.put('載入現有資料...')
            fetcher = YouTubeFetcher(settings)
            videos, transcripts, comments = fetcher.load_cached(channel_id)
            msg_queue.put(f'共 {len(videos)} 支影片，開始分析...')

            analyzer = ChannelAnalyzer(llm=llm, data_dir=settings.data_dir, out_dir=out_dir)
            analyzer.analyze(
                channel_id=channel_id, channel_title=channel_title,
                videos=videos, transcripts=transcripts, all_comments=comments,
                last_fetched=last_fetched,
            )

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            msg_queue.put('DONE:' + json.dumps({'success': True, 'summary': summary}))
        except Exception as e:
            import traceback
            msg_queue.put('ERROR:' + str(e) + '\n' + traceback.format_exc())

    return _make_task(run)

@app.route('/api/channels/<channel_id>/fetch', methods=['POST'])
def fetch_only(channel_id):
    def run(msg_queue):
        try:
            settings = load_settings()
            out_dir = Path(settings.reports_dir) / channel_id
            summary_path = out_dir / 'summary.json'
            if not summary_path.exists():
                msg_queue.put('ERROR:找不到 summary.json，請先執行完整分析')
                return

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            channel_title = summary.get('channel_title', channel_id)
            last_fetched = summary.get('last_fetched', summary.get('last_updated'))

            msg_queue.put(f'補抓 {last_fetched[:10]} 之後的新影片...')
            fetcher = YouTubeFetcher(settings)
            _, _, videos, _, _, fetch_time = \
                fetcher.fetch_incremental(channel_id, channel_title, last_fetched)
            msg_queue.put(f'完成，共 {len(videos)} 支影片')

            summary['last_fetched'] = fetch_time
            summary['stats'] = summary.get('stats', {})
            summary['stats']['total_videos'] = len(videos)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

            msg_queue.put('DONE:' + json.dumps({'success': True, 'summary': summary}))
        except Exception as e:
            import traceback
            msg_queue.put('ERROR:' + str(e) + '\n' + traceback.format_exc())

    return _make_task(run)

@app.route('/api/reports/<channel_id>/<filename>', methods=['GET'])
def get_report(channel_id, filename):
    if not filename.endswith('.md'):
        return jsonify({'error': '只支援 .md 檔案'}), 400
    settings = load_settings()
    path = Path(settings.reports_dir) / channel_id / filename
    if not path.exists():
        return jsonify({'error': '找不到報告檔案'}), 404
    return path.read_text(encoding='utf-8'), 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
    try:
        import requests
        ollama_url = os.getenv('LOCAL_LLM_URL', 'http://localhost:11434/v1')
        response = requests.get(f'{ollama_url.replace("/v1", "")}/api/tags')

        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            return jsonify({'models': models})
        else:
            return jsonify({'models': []})
    except Exception as e:
        return jsonify({'models': [], 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
