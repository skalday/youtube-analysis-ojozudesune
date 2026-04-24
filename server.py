from flask import Flask, request, jsonify, send_from_directory, Response
from pathlib import Path
import os
import json
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
                channel_id, channel_title, videos, transcripts, comments = fetcher.fetch(channel)
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
