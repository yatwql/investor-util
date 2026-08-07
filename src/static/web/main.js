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
    // 输入模式（试算 trial / 正式 formal）相关控件
    els.modeRadios = document.querySelectorAll('input[name="input_mode"]');
    els.sourceRadios = document.querySelectorAll('input[name="use_existing"]');
    els.formalOptions = $('formal-options');
    els.formalWarning = $('formal-warning');
    els.formalHint = $('formal-hint');
    els.confirmOverwrite = $('confirm-overwrite');
    els.configPanel = $('config-panel');

    els.fileInput.addEventListener('change', onFileSelected);
    els.generateForm.addEventListener('submit', onSubmit);
    $('health-refresh').addEventListener('click', function () {
      loadHealth(true);
    });
    $('config-reload').addEventListener('click', function () {
      loadConfigEdit();
    });

    // 生成用途/输入来源模式切换：正式模式展开区 + 警示条 + 按钮态联动
    els.modeRadios.forEach(function (r) {
      r.addEventListener('change', onModeChange);
    });
    els.sourceRadios.forEach(function (r) {
      r.addEventListener('change', onModeChange);
    });
    if (els.confirmOverwrite) {
      els.confirmOverwrite.addEventListener('change', updateGenerateBtn);
    }
    // 初始按默认 trial 收敛表单状态（正式展开区收起、按钮态就绪）
    onModeChange();

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

    // 配置编辑面板（与 TUI 菜单一致）
    loadConfigEdit();

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

  /* ── 输入模式（试算 trial / 正式 formal）状态机 ──
   * 试算（默认）：读上传临时文件，快照隔离 web/ 域，不碰正式持仓。
   * 正式：覆盖/使用正式持仓文件，快照写共享主目录；分「上传覆盖」与
   *   「直接用存量」两种来源——用存量免上传，但正式模式均须勾选确认。
   */
  function currentMode() {
    var checked = document.querySelector('input[name="input_mode"]:checked');
    return checked ? checked.value : 'trial';
  }

  function currentSource() {
    var checked = document.querySelector('input[name="use_existing"]:checked');
    return checked ? checked.value : 'upload';
  }

  // 正式-用存量：无需上传，直接读正式持仓文件
  function isFormalExisting() {
    return currentMode() === 'formal' && currentSource() === 'existing';
  }

  function onModeChange() {
    var formal = currentMode() === 'formal';
    if (els.formalOptions) {
      els.formalOptions.hidden = !formal;
    }
    if (!formal && els.confirmOverwrite) {
      // 切回试算：清除正式覆盖确认勾选，避免残留状态误导后续提交
      els.confirmOverwrite.checked = false;
    }
    updateWarning();
    updateSourceHint();
    updateGenerateBtn();
  }

  // 警示条文案按输入来源动态（用存量不覆盖文件，措辞区分）
  function updateWarning() {
    if (!els.formalWarning) {
      return;
    }
    var path = els.formalWarning.dataset.holdings || '正式持仓文件';
    if (isFormalExisting()) {
      els.formalWarning.textContent =
        '将读取当前正式持仓文件 ' + path + ' 生成报告，并写入共享快照时间线（不会覆盖文件）';
    } else {
      els.formalWarning.textContent =
        '将覆盖 ' + path + '，旧文件备份为 .bak，并写入共享快照时间线';
    }
  }

  function updateSourceHint() {
    if (!els.formalHint) {
      return;
    }
    if (currentMode() !== 'formal') {
      setStatus(els.formalHint, '', '');
      return;
    }
    if (isFormalExisting()) {
      setStatus(els.formalHint, '无需上传，将直接读取正式持仓文件生成报告', 'ok');
    } else {
      setStatus(els.formalHint, '请先上传新文件，将覆盖正式持仓文件', 'busy');
    }
  }

  // 生成按钮可用性：试算/正式-上传须先上传；正式须勾选确认；正式-用存量免上传
  function updateGenerateBtn() {
    if (currentMode() !== 'formal') {
      els.generateBtn.disabled = !state.fileId;
      return;
    }
    if (els.confirmOverwrite && !els.confirmOverwrite.checked) {
      els.generateBtn.disabled = true;
      return;
    }
    if (isFormalExisting()) {
      els.generateBtn.disabled = false;
      return;
    }
    els.generateBtn.disabled = !state.fileId;
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
        updateGenerateBtn();
      })
      .catch(function (err) {
        setStatus(els.uploadStatus, err.message, 'error');
        updateGenerateBtn();
      });
  }

  /* ── 触发生成 ── */
  function onSubmit(e) {
    e.preventDefault();
    var existing = isFormalExisting();
    // 正式-用存量无需上传；其余模式须已上传
    if (!existing && !state.fileId) {
      return;
    }
    els.generateBtn.disabled = true;
    els.generateBtn.textContent = '正在提交...';
    els.generateError.textContent = '';

    var body = {
      report_type: els.reportType.value,
      // 历史走势/强制 LLM 开关：表单显式传值（默认值已在页面加载时按配置回填）
      fetch_history: els.historyFetch.checked,
      force_llm: els.forceLlm.checked,
      mode: currentMode(),
      use_existing: existing,
    };
    // 正式-用存量：直接读正式持仓文件，body 不携带 file_id
    // （后端 formal+use_existing 校验禁止携带，携带即 BAD_PARAM）
    if (!existing) {
      body.file_id = state.fileId;
    }

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
        updateGenerateBtn();
        els.generateBtn.textContent = '生成报告';
        if (err.errorCode === 'FILE_EXPIRED') {
          // 上传文件已过期/服务重启：重置流程引导重新上传
          resetFlow(err.message);
          return;
        }
        // HOLDINGS_MISSING 等运行期错误：文案直显服务端中文，不前端映射
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
    // 试算/正式-上传：上传文件已随 run 消费清理，需重新上传；
    // 正式-用存量：无需上传，直接重新生成（提示与焦点均不指向重新上传）
    updateGenerateBtn();
    els.generateBtn.textContent = '生成报告';
    if (isFormalExisting()) {
      setStatus(els.uploadStatus, '可直接重新生成（读取当前正式持仓文件）', 'ok');
    } else {
      els.fileInput.value = '';
      if (message) {
        setStatus(els.uploadStatus, message, 'busy');
      }
      els.fileInput.focus();
    }
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

  /* ── 配置编辑（与 TUI 菜单一致，即改即存）──
   * GET /api/config/edit 载入全量可编辑面 → 按 7 组分块渲染。
   * 保存语义即改即存（与 TUI「改一项存一项」一致）：checkbox/radio 改动即
   * POST /api/config/edit；自由文本路径经各自「保存」按钮提交；对比指数池经
   * 添加/删除/重置动作提交。提交期间该控件禁用，成功回读该项最新值，失败
   * 恢复为改动前值并显示错误。
   * error_code 驱动分支（中文文案直显服务端，不前端硬编码映射）：
   *   BAD_PARAM(400) → 该分组错误区直显服务端中文；
   *   BAD_PARAM(403) → 面板顶部警示同源失败；
   *   CONFIG_WRITE_FAILED(500) → 分组错误区提示查看日志。
   * XSS 纪律：全部 textContent/DOM API 渲染，禁止 innerHTML。
   */
  var configState = { surface: null };

  // 控件中文标签（对齐 TUI 菜单 / 注册表中文名）
  var CONFIG_LABELS = {
    paths: { holdings_dir: '持仓目录', holdings_filename: '持仓文件名', output_dir: '输出目录' },
    sections: {
      enable_fund_deep_analysis: '基金深度分析',
      enable_news: '市场新闻',
      enable_history: '组合历史走势+回撤',
      enable_portfolio_evolution: '组合演进',
      enable_action: '行动建议'
    },
    submodules: {
      data_quality: '数据质量仪表盘',
      industry_beta: '行业Beta子表',
      candidate_compare: '候选基金比较子表',
      cost_lots: '成本流水',
      valuation_percentile: '估值分位',
      market_temperature: '市场温度'
    },
    llm: {
      global_macro: '全球政经局势',
      expert_review: '智囊团深度复盘',
      health_check: '持仓体检报告',
      penetration_deep: '穿透深度分析',
      news_correlation: '财经新闻热点与持仓关联分析'
    },
    debate: {
      llm_debate_procon: '辩论-正反辩论',
      llm_debate_conditional: '辩论-条件推理',
      llm_debate_qa_concentration: '辩论-集中度问答'
    }
  };

  // 持仓匿名化枚举中文描述（对齐 config/anonymizer.ANONYMIZATION_MODE_DESCRIPTIONS）
  var ANON_LABELS = {
    off: '关闭 — 显示真实持仓名称和代码',
    code_display: '代码显示 — 名称替换为\'品种X\'，保留代码和盈亏',
    full_anonymous: '完全匿名 — 名称\'品种X\'，代码\'000XXX\'，盈亏±XX%',
    summary: '汇总模式 — 仅显示大类汇总，不展示单条持仓'
  };

  function loadConfigEdit() {
    els.configPanel.textContent = '';
    var busy = document.createElement('p');
    busy.className = 'status-text status-busy';
    busy.textContent = '正在加载配置...';
    els.configPanel.appendChild(busy);
    fetch('/api/config/edit', { signal: AbortSignal.timeout(10000) })
      .then(handleResponse)
      .then(renderConfigEdit)
      .catch(function () {
        els.configPanel.textContent = '';
        var p = document.createElement('p');
        p.className = 'status-text status-error';
        p.textContent = '配置加载失败，请稍后重试';
        els.configPanel.appendChild(p);
      });
  }

  function renderConfigEdit(surface) {
    configState.surface = surface;
    els.configPanel.textContent = '';
    // 面板顶部警示区（同源失败 403 专用）
    var panelErr = document.createElement('p');
    panelErr.id = 'config-panel-error';
    panelErr.className = 'status-text status-error';
    panelErr.setAttribute('role', 'alert');
    panelErr.hidden = true;
    els.configPanel.appendChild(panelErr);

    els.configPanel.appendChild(renderPathsGroup(surface.paths));
    els.configPanel.appendChild(
      renderBoolGroup('sections', '报告章节', surface.sections, {})
    );
    els.configPanel.appendChild(
      renderBoolGroup('submodules', '报告增强子模块', surface.submodules, { prefix: 'report_submodules.' })
    );
    els.configPanel.appendChild(renderAnonGroup(surface.anonymization));
    els.configPanel.appendChild(renderIndicesGroup(surface));
    els.configPanel.appendChild(
      renderBoolGroup('llm', 'LLM 分析章节', surface.llm.enabled_llm, {
        prefix: 'enabled_llm.',
        note: '辩论三模块（白脸/黑脸/综合）不在菜单展示，输出由下方「辩论实验功能」三个开关控制'
      })
    );
    els.configPanel.appendChild(
      renderBoolGroup('debate', '辩论实验功能（⚗ 实验性，默认关闭）', surface.llm.debate, {
        experimental: true
      })
    );
  }

  function renderPathsGroup(paths) {
    var group = document.createElement('div');
    group.className = 'config-group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', '路径与文件');
    var heading = document.createElement('h3');
    heading.className = 'config-group-title';
    heading.textContent = '路径与文件';
    group.appendChild(heading);

    Object.keys(paths).forEach(function (key) {
      var row = document.createElement('div');
      row.className = 'config-path-row';
      var label = document.createElement('label');
      label.className = 'config-path-label';
      label.textContent = (CONFIG_LABELS.paths[key] || key) + '：';
      label.htmlFor = 'config-input-' + key;
      var input = document.createElement('input');
      input.type = 'text';
      input.id = 'config-input-' + key;
      input.value = paths[key] || '';
      input.spellcheck = false;
      input.autocomplete = 'off';
      var saveBtn = document.createElement('button');
      saveBtn.type = 'button';
      saveBtn.className = 'btn btn-secondary btn-sm config-save';
      saveBtn.textContent = '保存';
      saveBtn.addEventListener('click', onPathSave);
      var status = document.createElement('span');
      status.className = 'config-row-status';
      status.setAttribute('role', 'status');
      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(saveBtn);
      row.appendChild(status);
      group.appendChild(row);
    });

    group.appendChild(makeGroupErrorEl());
    return group;
  }

  function renderBoolGroup(groupKey, title, items, opts) {
    var groupId = 'config-group-' + groupKey;
    var group = document.createElement('div');
    group.className = 'config-group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-labelledby', groupId);
    var heading = document.createElement('h3');
    heading.id = groupId;
    heading.className = 'config-group-title';
    heading.textContent = title;
    group.appendChild(heading);

    Object.keys(items).forEach(function (key) {
      var fullKey = opts && opts.prefix ? opts.prefix + key : key;
      var label = (CONFIG_LABELS[groupKey] && CONFIG_LABELS[groupKey][key]) || key;
      if (opts && opts.experimental) {
        label = '⚗ ' + label;
      }
      var row = document.createElement('label');
      row.className = 'check-label config-row';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!items[key];
      cb.dataset.configKey = fullKey;
      cb.addEventListener('change', onConfigToggle);
      row.appendChild(cb);
      var span = document.createElement('span');
      span.textContent = label;
      row.appendChild(span);
      group.appendChild(row);
    });

    if (opts && opts.note) {
      var note = document.createElement('p');
      note.className = 'config-note-sub';
      note.textContent = opts.note;
      group.appendChild(note);
    }

    group.appendChild(makeGroupErrorEl());
    return group;
  }

  function renderAnonGroup(anon) {
    var group = document.createElement('div');
    group.className = 'config-group';
    group.setAttribute('role', 'radiogroup');
    group.setAttribute('aria-label', '持仓匿名化');
    var heading = document.createElement('h3');
    heading.className = 'config-group-title';
    heading.textContent = '持仓匿名化';
    group.appendChild(heading);

    (anon.options || []).forEach(function (mode) {
      var row = document.createElement('label');
      row.className = 'radio-label config-row';
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'config-anonymization';
      radio.value = mode;
      radio.checked = mode === anon.mode;
      radio.dataset.configKey = 'anonymization.mode';
      radio.addEventListener('change', onConfigRadioChange);
      row.appendChild(radio);
      var span = document.createElement('span');
      span.textContent = ANON_LABELS[mode] || mode;
      row.appendChild(span);
      group.appendChild(row);
    });

    group.appendChild(makeGroupErrorEl());
    return group;
  }

  function renderIndicesGroup(surface) {
    var group = document.createElement('div');
    group.className = 'config-group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', '对比指数池');
    var heading = document.createElement('h3');
    heading.className = 'config-group-title';
    heading.textContent = '对比指数池';
    group.appendChild(heading);

    var listWrap = document.createElement('div');
    listWrap.className = 'config-indices-list';
    renderIndicesList(listWrap, surface.comparison_indices);
    group.appendChild(listWrap);

    var addRow = document.createElement('div');
    addRow.className = 'config-indices-add';
    var codeInput = document.createElement('input');
    codeInput.type = 'text';
    codeInput.id = 'config-index-code';
    codeInput.placeholder = '指数代码（如 sh000905）';
    codeInput.autocomplete = 'off';
    codeInput.spellcheck = false;
    var nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.id = 'config-index-name';
    nameInput.placeholder = '指数名称（如 中证500）';
    nameInput.autocomplete = 'off';
    nameInput.spellcheck = false;
    var addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-secondary btn-sm';
    addBtn.textContent = '添加';
    addBtn.addEventListener('click', onIndexAdd);
    addRow.appendChild(codeInput);
    addRow.appendChild(nameInput);
    addRow.appendChild(addBtn);
    group.appendChild(addRow);

    var resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'btn btn-secondary btn-sm config-index-reset';
    resetBtn.textContent = '重置为默认预设';
    resetBtn.addEventListener('click', onIndexReset);
    group.appendChild(resetBtn);

    group.appendChild(makeGroupErrorEl());
    return group;
  }

  function renderIndicesList(wrap, indices) {
    wrap.textContent = '';
    var entries = Object.keys(indices || {});
    if (!entries.length) {
      var empty = document.createElement('p');
      empty.className = 'config-note-sub';
      empty.textContent = '空池（仅显示沪深300）';
      wrap.appendChild(empty);
      return;
    }
    entries.forEach(function (code) {
      var row = document.createElement('div');
      row.className = 'config-index-row';
      var name = document.createElement('span');
      name.className = 'config-index-name';
      name.textContent = code + ' (' + indices[code] + ')';
      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'btn btn-secondary btn-sm config-index-del';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', onIndexRemove);
      row.appendChild(name);
      row.appendChild(delBtn);
      wrap.appendChild(row);
    });
  }

  /* ── 即改即存：提交 POST /api/config/edit ── */
  function postConfigEdit(body) {
    return fetch('/api/config/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000)
    })
      .then(handleResponse)
      .then(function (data) {
        // 成功即清除面板顶部同源警示，避免残留误导
        var panelErr = document.getElementById('config-panel-error');
        if (panelErr) {
          panelErr.hidden = true;
          panelErr.textContent = '';
        }
        return data;
      });
  }

  function onConfigToggle(e) {
    var cb = e.target;
    var key = cb.dataset.configKey;
    var prev = !cb.checked; // change 后 checked 已是新值，取反得改动前值
    var group = cb.closest('.config-group');
    cb.disabled = true;
    clearGroupError(group);
    postConfigEdit({ key: key, value: cb.checked })
      .catch(function (err) {
        cb.checked = prev; // 失败恢复为改动前值
        showGroupError(group, err);
      })
      .then(function () {
        cb.disabled = false;
      });
  }

  function onConfigRadioChange(e) {
    var radio = e.target;
    if (!radio.checked) {
      return; // 仅处理选中变化
    }
    var prev = configState.surface.anonymization.mode;
    var group = radio.closest('.config-group');
    var radios = group.querySelectorAll('input[type="radio"]');
    radios.forEach(function (r) {
      r.disabled = true;
    });
    clearGroupError(group);
    postConfigEdit({ key: 'anonymization.mode', value: radio.value })
      .then(function () {
        configState.surface.anonymization.mode = radio.value;
      })
      .catch(function (err) {
        var target = group.querySelector('input[value="' + prev + '"]');
        if (target) {
          target.checked = true;
        }
        showGroupError(group, err);
      })
      .then(function () {
        radios.forEach(function (r) {
          r.disabled = false;
        });
      });
  }

  function onPathSave(e) {
    var btn = e.target;
    var row = btn.closest('.config-path-row');
    var input = row.querySelector('input[type="text"]');
    var key = input.id.replace('config-input-', '');
    var prev = input.value;
    var group = btn.closest('.config-group');
    var status = row.querySelector('.config-row-status');
    btn.disabled = true;
    status.textContent = '';
    status.className = 'config-row-status';
    clearGroupError(group);
    postConfigEdit({ key: key, value: input.value })
      .then(function (data) {
        input.value = data.value;
        status.textContent = data.backup ? '已保存（已备份）' : '已保存';
        status.className = 'config-row-status status-ok';
      })
      .catch(function (err) {
        input.value = prev; // 失败恢复为改动前值
        showGroupError(group, err);
      })
      .then(function () {
        btn.disabled = false;
      });
  }

  function onIndexAdd(e) {
    var btn = e.target;
    var group = btn.closest('.config-group');
    var codeInput = document.getElementById('config-index-code');
    var nameInput = document.getElementById('config-index-name');
    var code = codeInput.value.trim();
    var name = nameInput.value.trim();
    if (!code || !name) {
      showGroupError(group, { message: '指数代码与名称均不能为空' });
      return;
    }
    btn.disabled = true;
    clearGroupError(group);
    postConfigEdit({ key: 'comparison_indices', action: 'add', code: code, name: name })
      .then(function (data) {
        configState.surface.comparison_indices = data.value;
        codeInput.value = '';
        nameInput.value = '';
        var listWrap = group.querySelector('.config-indices-list');
        renderIndicesList(listWrap, data.value);
      })
      .catch(function (err) {
        showGroupError(group, err);
      })
      .then(function () {
        btn.disabled = false;
      });
  }

  function onIndexRemove(e) {
    var btn = e.target;
    var group = btn.closest('.config-group');
    var row = btn.closest('.config-index-row');
    var code = row.querySelector('.config-index-name').textContent.split(' (')[0];
    btn.disabled = true;
    clearGroupError(group);
    postConfigEdit({ key: 'comparison_indices', action: 'remove', code: code })
      .then(function (data) {
        configState.surface.comparison_indices = data.value;
        var listWrap = group.querySelector('.config-indices-list');
        renderIndicesList(listWrap, data.value);
      })
      .catch(function (err) {
        showGroupError(group, err);
      })
      .then(function () {
        btn.disabled = false;
      });
  }

  function onIndexReset(e) {
    var btn = e.target;
    var group = btn.closest('.config-group');
    var defaults = (configState.surface && configState.surface.comparison_indices_defaults) || {};
    var names = Object.keys(defaults)
      .map(function (c) {
        return c + ' (' + defaults[c] + ')';
      })
      .join('，');
    var confirmMsg = '确定重置对比指数池为默认预设？' + (names ? '（' + names + '）' : '');
    if (!window.confirm(confirmMsg)) {
      return;
    }
    btn.disabled = true;
    clearGroupError(group);
    postConfigEdit({ key: 'comparison_indices', action: 'reset' })
      .then(function (data) {
        configState.surface.comparison_indices = data.value;
        var listWrap = group.querySelector('.config-indices-list');
        renderIndicesList(listWrap, data.value);
      })
      .catch(function (err) {
        showGroupError(group, err);
      })
      .then(function () {
        btn.disabled = false;
      });
  }

  /* ── 分组错误区辅助 ── */
  function makeGroupErrorEl() {
    var el = document.createElement('p');
    el.className = 'status-text config-error';
    el.setAttribute('role', 'alert');
    el.hidden = true;
    return el;
  }

  function clearGroupError(group) {
    var err = group.querySelector('.config-error');
    if (err) {
      err.hidden = true;
      err.textContent = '';
    }
  }

  function showGroupError(group, err) {
    if (err.errorCode === 'BAD_PARAM' && err.httpStatus === 403) {
      // 同源失败 → 面板顶部警示，提示刷新
      var panelErr = document.getElementById('config-panel-error');
      if (panelErr) {
        panelErr.textContent = '同源校验失败，请刷新页面重试';
        panelErr.hidden = false;
      }
      return;
    }
    var msg = err.message || '配置修改失败';
    var errEl = group.querySelector('.config-error');
    if (!errEl) {
      errEl = makeGroupErrorEl();
      group.appendChild(errEl);
    }
    errEl.textContent = msg;
    errEl.hidden = false;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
