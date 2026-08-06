/* main.js — Web UI 前端逻辑（原生 ES6，无构建链）。
 *
 * 链路：上传 → 选择报告格式/选项 → 提交 → 轮询进度（编号步骤 + 当前阶段）
 * → 完成后产物按钮；状态区展示数据源健康 + 历史运行记录。
 *
 * XSS 防护（渲染侧）：一律 textContent/DOM API 渲染服务端返回字符串
 * （errors/events/健康/历史，可能含数据源名等不可信内容），禁止 innerHTML。
 * 错误展示：取服务端 error 中文文案直显；error_code 驱动分支动作，
 * 中文文案不前端硬编码映射（避免服务端/前端文案漂移）。
 */
(function () {
  'use strict';

  var POLL_INTERVAL_MS = 2000;

  var state = {
    fileId: null,
    uploadInfo: null,
    runId: null,
    lastSeq: 0,
    pollTimer: null,
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  /* ── 初始化 ── */
  function init() {
    els.fileInput = $('file-input');
    els.uploadStatus = $('upload-status');
    els.generateForm = $('generate-form');
    els.reportType = $('report-type');
    els.historyFetch = $('history-fetch');
    els.forceLlm = $('force-llm');
    els.generateBtn = $('generate-btn');
    els.generateError = $('generate-error');
    els.progressSection = $('progress-section');
    els.progressBar = $('progress-bar');
    els.progressPhase = $('progress-phase');
    els.progressEvents = $('progress-events');
    els.resultSection = $('result-section');
    els.resultActions = $('result-actions');
    els.resultErrors = $('result-errors');
    els.resultFooter = $('result-footer');
    els.healthList = $('health-list');
    els.historyList = $('history-list');

    els.fileInput.addEventListener('change', onFileSelected);
    els.generateForm.addEventListener('submit', onSubmit);
    $('health-refresh').addEventListener('click', function () {
      loadHealth(true);
    });

    // 拖拽上传（拖入上传区高亮）
    var zone = document.querySelector('.upload-zone');
    ['dragenter', 'dragover'].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        zone.classList.add('drag-over');
      });
    });
    ['dragleave', 'drop'].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        zone.classList.remove('drag-over');
      });
    });
    zone.addEventListener('drop', function (e) {
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) {
        els.fileInput.files = e.dataTransfer.files;
        onFileSelected();
      }
    });

    // 状态区：数据源健康 + 历史运行记录（服务端各有短缓存，非频繁轮询）
    loadHealth(false);
    loadHistory();

    // 轮询节流：页面不可见时暂停轮询，恢复可见立即同步一次（省流量/省请求）
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        stopPolling();
      } else if (state.runId && els.progressSection && !els.progressSection.hidden) {
        startPolling();
      }
    });
  }

  /* ── 响应信封解析 ──
   * 成功：{ok:true, data} ；错误：{ok:false, error_code, error}（HTTP 4xx/5xx）
   * 统一抛 Error，附带 errorCode/httpStatus 供分支。
   */
  function handleResponse(res) {
    return res
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        if (!res.ok || data.ok === false) {
          var err = new Error(data.error || '请求失败（HTTP ' + res.status + '）');
          err.errorCode = data.error_code || null;
          err.httpStatus = res.status;
          throw err;
        }
        return data.data;
      });
  }

  function setStatus(el, msg, kind) {
    el.textContent = msg;
    el.className = 'status-text' + (kind ? ' status-' + kind : '');
  }

  /* ── 上传 ── */
  function onFileSelected() {
    var file = els.fileInput.files[0];
    if (!file) {
      return;
    }
    var fd = new FormData();
    fd.append('file', file);
    setStatus(els.uploadStatus, '正在上传并校验 ' + file.name + ' ...', 'busy');
    els.generateBtn.disabled = true;

    fetch('/api/upload', {
      method: 'POST',
      body: fd,
      signal: AbortSignal.timeout(10000),
    })
      .then(handleResponse)
      .then(function (data) {
        state.fileId = data.file_id;
        state.uploadInfo = data;
        var accountText = data.sheets && data.sheets.length
          ? data.sheets.length + ' 个账户'
          : '1 个账户';
        setStatus(els.uploadStatus, '上传成功：' + accountText + '，共 ' + data.count + ' 条持仓，可生成报告', 'ok');
        els.generateBtn.disabled = false;
      })
      .catch(function (err) {
        setStatus(els.uploadStatus, err.message, 'error');
      });
  }

  /* ── 触发生成 ── */
  function onSubmit(e) {
    e.preventDefault();
    if (!state.fileId) {
      return;
    }
    els.generateBtn.disabled = true;
    els.generateBtn.textContent = '正在提交...';
    els.generateError.textContent = '';

    var body = {
      file_id: state.fileId,
      report_type: els.reportType.value,
      // 历史走势/强制 LLM 开关：表单显式传值（默认值已在页面加载时按配置回填）
      fetch_history: els.historyFetch.checked,
      force_llm: els.forceLlm.checked,
    };

    fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    })
      .then(handleResponse)
      .then(function (data) {
        state.runId = data.run_id;
        state.lastSeq = 0;
        els.generateBtn.textContent = '生成中...';
        showProgress();
        startPolling();
      })
      .catch(function (err) {
        els.generateBtn.disabled = false;
        els.generateBtn.textContent = '生成报告';
        if (err.errorCode === 'FILE_EXPIRED') {
          // 上传文件已过期/服务重启：重置流程引导重新上传
          resetFlow(err.message);
          return;
        }
        els.generateError.textContent = err.message;
      });
  }

  /* ── 进度轮询 ── */
  function showProgress() {
    els.progressSection.hidden = false;
    els.resultSection.hidden = true;
    els.progressEvents.textContent = '';
    els.progressPhase.textContent = '准备中...';
    els.progressBar.style.width = '0%';
    els.progressBar.setAttribute('aria-valuenow', '0');
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
    pollOnce();
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function pollOnce() {
    fetch('/api/runs/' + encodeURIComponent(state.runId) + '/events?after=' + state.lastSeq, {
      signal: AbortSignal.timeout(10000),
    })
      .then(handleResponse)
      .then(function (data) {
        appendEvents(data.events || []);
        if (data.last_seq > state.lastSeq) {
          state.lastSeq = data.last_seq;
        }
        if (data.status === 'done' || data.status === 'failed') {
          stopPolling();
          loadResult();
        }
      })
      .catch(function () {
        // 轮询瞬时失败静默，下一周期重试（网络抖动不中断流程）
      });
  }

  function appendEvents(events) {
    events.forEach(function (ev) {
      var li = document.createElement('li');
      li.className = 'event event-' + ev.level;
      var num = document.createElement('span');
      num.className = 'event-seq';
      num.textContent = String(ev.seq);
      var icon = document.createElement('span');
      icon.className = 'event-icon';
      icon.textContent = eventIcon(ev.level);
      var text = document.createElement('span');
      text.textContent = ev.message;
      li.appendChild(num);
      li.appendChild(icon);
      li.appendChild(text);
      els.progressEvents.appendChild(li);
    });
    var last = events[events.length - 1];
    if (last) {
      // 阶段名 + 序号：以事件消息为当前阶段描述，seq 为步序
      els.progressPhase.textContent = '当前阶段（第 ' + last.seq + ' 步）：' + last.message;
    }
    // 无总步数，按已见步骤数估算（封顶 90%，完成时置 100%）
    var pct = Math.min(90, els.progressEvents.children.length);
    els.progressBar.style.width = pct + '%';
    els.progressBar.setAttribute('aria-valuenow', String(pct));
    els.progressEvents.scrollTop = els.progressEvents.scrollHeight;
  }

  function eventIcon(level) {
    if (level === 'ok') {
      return '✓';
    }
    if (level === 'warn') {
      return '!';
    }
    if (level === 'error') {
      return '✕';
    }
    return '·';
  }

  /* ── 结果 ── */
  function loadResult() {
    fetch('/api/runs/' + encodeURIComponent(state.runId), {
      signal: AbortSignal.timeout(10000),
    })
      .then(handleResponse)
      .then(function (data) {
        if (data.status === 'done') {
          els.progressBar.style.width = '100%';
          els.progressBar.setAttribute('aria-valuenow', '100');
          els.progressPhase.textContent = '全部完成';
          renderResultState(data.exit_code, data.errors || [], data.artifacts || []);
        } else {
          renderResultState(
            2,
            data.errors && data.errors.length ? data.errors : ['任务执行失败（详情请查看日志）'],
            []
          );
        }
      })
      .catch(function (err) {
        renderResultState(2, [err.message], []);
      });
  }

  function renderResultState(exitCode, errors, artifacts) {
    els.resultActions.textContent = '';
    els.resultErrors.textContent = '';
    els.resultFooter.textContent = '';

    var badge = document.createElement('p');
    badge.className = 'result-badge result-badge-' + (exitCode === 0 ? 'ok' : exitCode === 1 ? 'warn' : 'error');
    badge.textContent = exitCode === 0 ? '报告生成成功' : exitCode === 1 ? '报告已生成，部分模块遇到问题' : '报告生成失败';
    els.resultErrors.appendChild(badge);

    if (errors.length) {
      var list = document.createElement('ul');
      errors.forEach(function (msg) {
        var li = document.createElement('li');
        li.textContent = msg;
        list.appendChild(li);
      });
      els.resultErrors.appendChild(list);
    }

    if (exitCode === 1) {
      var tip = document.createElement('p');
      tip.className = 'result-tip';
      tip.textContent = '提示：部分数据源暂不可用或模块未完成，已生成的结果可正常预览/下载，可稍后重新生成重试。';
      els.resultErrors.appendChild(tip);
    } else if (exitCode === 2) {
      var tip2 = document.createElement('p');
      tip2.className = 'result-tip';
      tip2.textContent = '提示：请查看日志 logs/app.log 了解详情，稍后重试。';
      els.resultErrors.appendChild(tip2);
      var retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'btn btn-primary';
      retry.textContent = '重新生成';
      retry.addEventListener('click', function () {
        // 上传文件已随 run 消费清理，重新生成需重新上传
        resetFlow('重新生成请重新上传持仓文件');
      });
      els.resultFooter.appendChild(retry);
    }

    renderArtifacts(artifacts);
    els.resultSection.hidden = false;
  }

  function renderArtifacts(artifacts) {
    if (!artifacts.length) {
      return;
    }
    artifacts.forEach(function (a) {
      var url = '/api/reports/' + encodeURIComponent(a.path);
      if (a.kind === 'html') {
        var preview = document.createElement('a');
        preview.className = 'btn btn-primary';
        preview.textContent = '预览 ' + a.name;
        preview.href = url;
        preview.target = '_blank';
        preview.rel = 'noopener';
        els.resultActions.appendChild(preview);
      }
      var download = document.createElement('a');
      download.className = 'btn btn-secondary';
      download.textContent = '下载 ' + a.name;
      download.href = url;
      download.download = a.path;
      els.resultActions.appendChild(download);
    });
  }

  function resetFlow(message) {
    stopPolling();
    state.fileId = null;
    state.uploadInfo = null;
    state.runId = null;
    state.lastSeq = 0;
    els.progressSection.hidden = true;
    els.resultSection.hidden = true;
    els.generateError.textContent = '';
    // 文件已消费/失效，重新生成需重新上传（按钮禁用直至新上传）
    els.generateBtn.disabled = true;
    els.generateBtn.textContent = '生成报告';
    els.fileInput.value = '';
    if (message) {
      setStatus(els.uploadStatus, message, 'busy');
    }
    els.fileInput.focus();
  }

  /* ── 状态区：数据源健康 ── */
  function loadHealth(fresh) {
    els.healthList.textContent = '';
    var busy = document.createElement('p');
    busy.className = 'status-text status-busy';
    busy.textContent = fresh ? '重新检测中...' : '正在检测...';
    els.healthList.appendChild(busy);

    fetch('/api/health' + (fresh ? '?fresh=1' : ''), {
      signal: AbortSignal.timeout(15000),
    })
      .then(handleResponse)
      .then(function (results) {
        renderHealth(results || []);
      })
      .catch(function () {
        els.healthList.textContent = '';
        var p = document.createElement('p');
        p.className = 'status-text status-error';
        p.textContent = '健康检测失败，请稍后重试';
        els.healthList.appendChild(p);
      });
  }

  function renderHealth(results) {
    els.healthList.textContent = '';
    if (!results.length) {
      var p = document.createElement('p');
      p.className = 'status-text status-busy';
      p.textContent = '暂无数据源检测结果';
      els.healthList.appendChild(p);
      return;
    }
    results.forEach(function (item) {
      var row = document.createElement('div');
      row.className = 'health-row ' + (item.ok ? 'health-ok' : 'health-err');
      var name = document.createElement('span');
      name.className = 'health-name';
      name.textContent = item.label || item.name;
      var status = document.createElement('span');
      status.className = 'health-status';
      status.textContent = item.ok ? '正常' : '异常';
      var meta = document.createElement('span');
      meta.className = 'health-meta';
      meta.textContent = item.ok ? item.latency_ms + 'ms' : (item.message || '不可用');
      row.appendChild(name);
      row.appendChild(status);
      row.appendChild(meta);
      els.healthList.appendChild(row);
    });
  }

  /* ── 状态区：历史运行记录 ── */
  function loadHistory() {
    fetch('/api/runs/history', {
      signal: AbortSignal.timeout(10000),
    })
      .then(handleResponse)
      .then(function (records) {
        renderHistory(records || []);
      })
      .catch(function () {
        els.historyList.textContent = '';
        var p = document.createElement('p');
        p.className = 'status-text status-error';
        p.textContent = '历史记录加载失败';
        els.historyList.appendChild(p);
      });
  }

  function renderHistory(records) {
    els.historyList.textContent = '';
    if (!records.length) {
      var p = document.createElement('p');
      p.className = 'status-text status-busy';
      p.textContent = '暂无历史运行记录';
      els.historyList.appendChild(p);
      return;
    }
    var list = document.createElement('ul');
    records.slice(0, 10).forEach(function (rec) {
      var li = document.createElement('li');
      li.className = 'history-row';
      var when = document.createElement('span');
      when.className = 'history-time';
      when.textContent = formatTs(rec.timestamp);
      var type = document.createElement('span');
      type.className = 'history-type';
      type.textContent = (rec.report_type || 'basic').toUpperCase();
      var meta = document.createElement('span');
      meta.className = 'history-meta';
      meta.textContent = rec.holdings_count + ' 条 · ' + (rec.total_seconds || 0) + 's';
      li.appendChild(when);
      li.appendChild(type);
      li.appendChild(meta);
      if (rec.errors && rec.errors.length) {
        var errBadge = document.createElement('span');
        errBadge.className = 'history-err';
        errBadge.textContent = '有异常';
        li.appendChild(errBadge);
      }
      list.appendChild(li);
    });
    els.historyList.appendChild(list);
  }

  function formatTs(ts) {
    if (!ts) {
      return '-';
    }
    var d = new Date(ts);
    if (isNaN(d.getTime())) {
      return String(ts);
    }
    function pad(n) {
      return n < 10 ? '0' + n : String(n);
    }
    return (
      d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
    );
  }

  document.addEventListener('DOMContentLoaded', init);
})();
