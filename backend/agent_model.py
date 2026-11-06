"""Bounded multimodal API call using the existing Hermes Z.ai credential resolver.

No Hermes personal memory, tools, sessions, or config files are modified.
Only the final structured reply and non-secret request receipt leave this process.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

MODEL = 'glm-5.3-flash'


def main():
    os.environ['HERMES_DISABLE_LAZY_INSTALLS'] = '1'
    root = Path.home() / '.hermes/hermes-agent'
    sys.path.insert(0, str(root))
    from pm.environments import project_python
    python = project_python(root)
    if Path(sys.prefix) != python.parent.parent:
        os.execv(str(python), [str(python), str(Path(__file__).resolve())])
    payload = json.load(sys.stdin)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from hermes_cli.env_loader import load_hermes_dotenv
        from hermes_cli.runtime_provider import resolve_runtime_provider
        load_hermes_dotenv()
        runtime = resolve_runtime_provider(requested='zai', target_model=MODEL)
    if runtime.get('provider') != 'zai' or not runtime.get('api_key'):
        raise ValueError('Hermes Z.ai 配置不可用')
    body = {'model': MODEL, 'messages': payload['messages'], 'temperature': 1.0,
            'max_tokens': 16384, 'reasoning_effort': 'max', 'thinking': {'type': 'enabled'},
            'response_format': {'type': 'json_object'}, 'stream': False}
    request = urllib.request.Request(runtime['base_url'].rstrip('/') + '/chat/completions',
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + runtime['api_key']})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        raise ValueError(f'模型服务返回 HTTP {error.code}') from None
    except (OSError, ValueError):
        raise ValueError('模型连接超时或响应无效') from None
    choice = result.get('choices', [{}])[0]
    if choice.get('finish_reason') == 'length':
        raise ValueError('模型回答未完成，请缩小本次登记内容后重试')
    raw = choice.get('message', {}).get('content', '').strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0]
    answer = json.loads(raw)
    if not isinstance(answer, dict) or not isinstance(answer.get('reply'), str):
        raise ValueError('模型未返回有效登记内容，请重试')
    print(json.dumps({'answer': answer, 'receipt': {'requestedModel': MODEL,
        'returnedModel': result.get('model'), 'provider': 'zai', 'reasoningEffort': 'max',
        'requestId': result.get('id'), 'seconds': round(time.monotonic() - started, 2),
        'usage': result.get('usage', {}), 'imageCount': sum(
            c.get('type') == 'image_url' for m in payload['messages']
            for c in m.get('content', []) if isinstance(c, dict))}}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error': str(error)[:180] if isinstance(error, ValueError)
                          else '模型调用失败，请稍后重试'}, ensure_ascii=False))
        sys.exit(1)
