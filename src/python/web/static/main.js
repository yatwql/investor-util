/* main.js — Web UI 前端逻辑（原生 ES6，无构建链）。
 *
 * 阶段 1 链路：上传 → 选择报告格式 → 提交 → 轮询进度 → 完成后产物按钮。
 *
 * XSS 防护（渲染侧）：一律 textContent/DOM API 渲染服务端返回字符串
 * （errors/events，可能含数据源名等不可信内容），禁止 innerHTML。
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
    els.generateBtn = $('generate-btn');
    els.generateError = $('generate-error');
    els.progressSection = $('progress-section');
    els.progressBar = $('progress-bar');
    els.progressEvents = $('progress-events');
    els.resultSection = $('result-section');
    els.resultActions = $('result-actions');
    els.resultErrors = $('result-errors');

    els.fileInput.addEventListener('change', onFileSelected);
    els.generateForm.addEventListener('submit', onSubmit);

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
    els.generateError.textContent = '';

    var body = {
      file_id: state.fileId,
      report_type: els.reportType.value,
      // 阶段 1：历史走势跟随配置（None → generate_report 按 config.history.fetch_mode 解析）
      fetch_history: null,
      force_llm: false,
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
        showProgress();
        startPolling();
      })
      .catch(function (err) {
        els.generateBtn.disabled = false;
        els.generateError.textContent = err.message;
        // RUN_QUEUE_FULL：已排队满，提示稍后再试（按钮态已恢复可重试）
        if (err.errorCode === 'RUN_QUEUE_FULL') {
          els.generateError.textContent = err.message;
        }
      });
  }

  /* ── 进度轮询 ── */
  function showProgress() {
    els.progressSection.hidden = false;
    els.resultSection.hidden = true;
    els.progressEvents.textContent = '';
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
      var icon = document.createElement('span');
      icon.className = 'event-icon';
      icon.textContent = eventIcon(ev.level);
      var text = document.createElement('span');
      text.textContent = ev.message;
      li.appendChild(icon);
      li.appendChild(text);
      els.progressEvents.appendChild(li);
    });
    els.progressBar.style.width = Math.min(100, els.progressEvents.children.length) + '%';
    els.progressBar.setAttribute('aria-valuenow', String(els.progressEvents.children.length));
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
          renderArtifacts(data.artifacts || []);
          renderErrors(data.errors || [], false);
        } else {
          var errors = data.errors && data.errors.length ? data.errors : ['任务执行失败（详情请查看日志）'];
          renderErrors(errors, true);
        }
      })
      .catch(function (err) {
        renderErrors([err.message], true);
      });
  }

  function renderArtifacts(artifacts) {
    els.resultActions.textContent = '';
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
    els.resultSection.hidden = false;
  }

  function renderErrors(errors, severe) {
    els.resultErrors.textContent = '';
    if (!errors.length) {
      return;
    }
    var heading = document.createElement('p');
    heading.className = 'result-errors-heading';
    heading.textContent = severe ? '生成未完整完成：' : '部分模块遇到问题：';
    els.resultErrors.appendChild(heading);
    var list = document.createElement('ul');
    errors.forEach(function (msg) {
      var li = document.createElement('li');
      li.textContent = msg;
      list.appendChild(li);
    });
    els.resultErrors.appendChild(list);
    els.resultSection.hidden = false;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
