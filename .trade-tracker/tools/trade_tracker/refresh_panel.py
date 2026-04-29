from __future__ import annotations

import re


def add_refresh_progress_panel(html_text: str) -> str:
    if 'id="refresh-panel"' in html_text:
        return html_text

    panel = """
          <section class="refresh-panel" id="refresh-panel" aria-live="polite">
            <div class="refresh-panel-head">
              <div>
                <p class="refresh-kicker">本地刷新</p>
                <h2>刷新看板</h2>
                <p>重新读取工作簿、更新行情、计算汇总并重建网页；下面会显示现在具体在等什么。</p>
              </div>
              <button class="refresh-button" type="button" data-refresh-start>刷新看板</button>
            </div>
            <div class="refresh-status-line">
              <span class="refresh-state" data-refresh-state>检测刷新服务</span>
              <span class="refresh-percent" data-refresh-percent>0%</span>
            </div>
            <div class="refresh-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
              <span data-refresh-bar></span>
            </div>
            <ol class="refresh-steps" data-refresh-steps>
              <li class="refresh-step is-muted">
                <strong>等待操作</strong>
                <span>双击 Update Preview.command 打开后，可以在这里直接刷新。</span>
              </li>
            </ol>
          </section>
"""
    card_match = re.search(r'<div class="index-card">.*?</div>', html_text, flags=re.S)
    if card_match:
        html_text = html_text[: card_match.end()] + "\n" + panel + html_text[card_match.end() :]
    else:
        body_match = re.search(r"<body[^>]*>", html_text, flags=re.I)
        if body_match:
            html_text = html_text[: body_match.end()] + "\n" + panel + html_text[body_match.end() :]
        else:
            html_text = panel + html_text

    style = """
        <style>
        .refresh-panel {
          margin: 18px 0 20px;
          padding: 18px;
          border: 1px solid rgba(196, 215, 202, 0.92);
          border-radius: 24px;
          background:
            radial-gradient(circle at 90% 12%, rgba(251, 188, 4, 0.20), transparent 110px),
            linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(239, 248, 241, 0.97));
          box-shadow: 0 18px 42px rgba(60, 64, 67, 0.08);
        }

        .refresh-panel-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 18px;
        }

        .refresh-kicker {
          margin: 0 0 5px;
          color: #137333;
          font-size: 12px;
          font-weight: 800;
          letter-spacing: 0.08em;
        }

        .refresh-panel h2 {
          margin: 0 0 6px;
          color: #202124;
          font-size: 22px;
          line-height: 1.18;
          letter-spacing: -0.035em;
        }

        .refresh-panel p {
          margin: 0;
          color: #5f6f63;
          font-size: 13px;
          line-height: 1.55;
        }

        .refresh-button {
          flex: 0 0 auto;
          border: 0;
          border-radius: 999px;
          padding: 10px 16px;
          color: #fff;
          background: linear-gradient(135deg, #137333, #34a853);
          box-shadow: 0 10px 24px rgba(19, 115, 51, 0.22);
          font-size: 13px;
          font-weight: 800;
          cursor: pointer;
        }

        .refresh-button:disabled {
          color: #7a867d;
          background: #dfe8e2;
          box-shadow: none;
          cursor: not-allowed;
        }

        .refresh-status-line {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-top: 16px;
          color: #466052;
          font-size: 12px;
          font-weight: 800;
        }

        .refresh-state {
          display: inline-flex;
          align-items: center;
          gap: 8px;
        }

        .refresh-state::before {
          content: "";
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: #fbbc04;
          box-shadow: 0 0 0 4px rgba(251, 188, 4, 0.16);
        }

        .refresh-panel.is-ready .refresh-state::before,
        .refresh-panel.is-done .refresh-state::before {
          background: #34a853;
          box-shadow: 0 0 0 4px rgba(52, 168, 83, 0.16);
        }

        .refresh-panel.is-error .refresh-state::before {
          background: #d93025;
          box-shadow: 0 0 0 4px rgba(217, 48, 37, 0.14);
        }

        .refresh-progress {
          height: 10px;
          margin-top: 8px;
          overflow: hidden;
          border-radius: 999px;
          background: #dfeae3;
        }

        .refresh-progress span {
          display: block;
          width: 0%;
          height: 100%;
          border-radius: inherit;
          background: linear-gradient(90deg, #34a853, #fbbc04);
          transition: width 220ms ease;
        }

        .refresh-steps {
          display: grid;
          gap: 8px;
          max-height: 190px;
          margin: 14px 0 0;
          padding: 0;
          overflow: auto;
          list-style: none;
        }

        .refresh-step {
          display: grid;
          grid-template-columns: minmax(96px, max-content) 1fr;
          gap: 12px;
          padding: 9px 11px;
          border: 1px solid rgba(196, 215, 202, 0.72);
          border-radius: 15px;
          background: rgba(255, 255, 255, 0.64);
          color: #5f6368;
          font-size: 12px;
        }

        .refresh-step strong {
          color: #202124;
          font-weight: 800;
        }

        .refresh-step.is-current {
          border-color: rgba(52, 168, 83, 0.44);
          background: rgba(232, 245, 233, 0.80);
        }

        .refresh-step.is-error {
          border-color: rgba(217, 48, 37, 0.24);
          background: rgba(252, 232, 230, 0.62);
        }

        .refresh-step.is-muted {
          color: #6f7d73;
        }

        @media (max-width: 760px) {
          .refresh-panel-head {
            display: grid;
          }

          .refresh-button {
            width: 100%;
          }

          .refresh-step {
            grid-template-columns: 1fr;
            gap: 4px;
          }
        }
        </style>
"""
    script = """
        <script>
        (function setupRefreshPanel() {
          const panel = document.getElementById('refresh-panel');
          if (!panel) return;

          const button = panel.querySelector('[data-refresh-start]');
          const state = panel.querySelector('[data-refresh-state]');
          const percent = panel.querySelector('[data-refresh-percent]');
          const bar = panel.querySelector('[data-refresh-bar]');
          const progress = panel.querySelector('.refresh-progress');
          const steps = panel.querySelector('[data-refresh-steps]');
          const localServer = 'http://127.0.0.1:8765';
          const apiBase = window.location.protocol === 'file:' ? localServer : '';
          let isRefreshing = false;

          function setStatus(text, tone) {
            state.textContent = text;
            panel.classList.remove('is-ready', 'is-running', 'is-done', 'is-error');
            if (tone) panel.classList.add(tone);
          }

          function setProgress(value) {
            const next = Math.max(0, Math.min(100, Number(value) || 0));
            percent.textContent = `${Math.round(next)}%`;
            bar.style.width = `${next}%`;
            progress.setAttribute('aria-valuenow', String(Math.round(next)));
          }

          function resetSteps() {
            steps.innerHTML = '';
          }

          function addStep(step, detail, tone) {
            steps.querySelectorAll('.is-current').forEach((item) => item.classList.remove('is-current'));
            const item = document.createElement('li');
            item.className = `refresh-step ${tone || 'is-current'}`;
            const title = document.createElement('strong');
            const body = document.createElement('span');
            title.textContent = step || '处理中';
            body.textContent = detail || '继续等待当前步骤完成。';
            item.append(title, body);
            steps.appendChild(item);
            while (steps.children.length > 26) {
              steps.firstElementChild.remove();
            }
            steps.scrollTop = steps.scrollHeight;
          }

          async function checkRefreshService() {
            button.disabled = true;
            setStatus('检测刷新服务', 'is-running');
            setProgress(0);

            if (!window.EventSource) {
              setStatus('浏览器不支持实时刷新', 'is-error');
              addStep('无法刷新', '当前浏览器不支持 EventSource，可以继续用 Update Preview.command 刷新。', 'is-error');
              return;
            }

            try {
              const response = await fetch(`${apiBase}/api/ping?ts=${Date.now()}`, { cache: 'no-store' });
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              button.disabled = false;
              setStatus('准备就绪', 'is-ready');
              addStep('刷新服务已连接', '点“刷新看板”后会实时显示每一步进度。', 'is-muted');
            } catch (_error) {
              setStatus('需要启动本地刷新服务', 'is-error');
              addStep('服务未连接', '请双击主目录里的 Update Preview.command，再从打开的网页刷新。', 'is-error');
            }
          }

          function reloadPreview(target) {
            setTimeout(() => {
              if (window.location.protocol === 'file:') {
                const base = window.location.href.split('#')[0].split('?')[0];
                window.location.replace(`${base}?ts=${Date.now()}`);
              } else {
                window.location.replace(target || `/preview/index.html?ts=${Date.now()}`);
              }
            }, 900);
          }

          button.addEventListener('click', () => {
            if (isRefreshing) return;
            isRefreshing = true;
            button.disabled = true;
            resetSteps();
            setProgress(1);
            setStatus('刷新中', 'is-running');
            addStep('开始刷新', '正在连接本地生成器。');

            let finished = false;
            const source = new EventSource(`${apiBase}/api/refresh?ts=${Date.now()}`);

            source.addEventListener('progress', (event) => {
              const payload = JSON.parse(event.data || '{}');
              setStatus(payload.step || '刷新中', 'is-running');
              if (payload.percent !== undefined) setProgress(payload.percent);
              addStep(payload.step, payload.detail);
            });

            source.addEventListener('log', (event) => {
              const payload = JSON.parse(event.data || '{}');
              if (payload.line) addStep('生成器输出', payload.line, 'is-muted');
            });

            source.addEventListener('done', (event) => {
              const payload = JSON.parse(event.data || '{}');
              finished = true;
              source.close();
              setProgress(100);
              setStatus('刷新完成，正在重载页面', 'is-done');
              addStep(payload.step || '完成', payload.detail || '页面已重新生成。', 'is-muted');
              reloadPreview(payload.reload);
            });

            source.addEventListener('error', (event) => {
              if (finished) return;
              let payload = {};
              try {
                payload = JSON.parse(event.data || '{}');
              } catch (_error) {
                payload = {};
              }
              finished = true;
              source.close();
              isRefreshing = false;
              button.disabled = false;
              setStatus('刷新失败', 'is-error');
              addStep(payload.step || '刷新失败', payload.detail || '连接断开或生成器报错。', 'is-error');
            });

            source.onerror = () => {
              if (finished) return;
              finished = true;
              source.close();
              isRefreshing = false;
              button.disabled = false;
              setStatus('刷新失败', 'is-error');
              addStep('连接中断', '本地刷新服务没有返回完成信号，可以看一下命令窗口里的错误。', 'is-error');
            };
          });

          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', checkRefreshService);
          } else {
            checkRefreshService();
          }
        })();
        </script>
"""
    if "</head>" in html_text:
        html_text = html_text.replace("</head>", style + "\n</head>", 1)
    else:
        html_text = style + html_text
    if "</body>" in html_text:
        return html_text.replace("</body>", script + "\n</body>", 1)
    return html_text + script
