/* ============================================================
 * 企业数字员工 · 数据分析集群 前端逻辑
 * 功能：登录鉴权、SSE 流式问答、打字机效果、四维 Judge 评审面板
 * ============================================================ */

(() => {
'use strict';

// ==================== 配置 ====================
const API = {
    LOGIN: '/api/auth/login',
    ME: '/api/auth/me',
    ASK: '/api/analysis/ask',
    STREAM: '/api/analysis/stream',
    HISTORY: '/api/analysis/history',
    MCP_TOOLS: '/api/analysis/mcp/tools',
};

// 四维评审维度定义
const JUDGE_DIMS = [
    { key: 'faithfulness',         label: '忠实度',         desc: '回答是否忠于检索事实，无幻觉', icon: '🛡️' },
    { key: 'context_relevancy',   label: '上下文相关性',   desc: '检索内容与问题的匹配度',     icon: '🎯' },
    { key: 'answer_relevancy',    label: '回答相关性',     desc: '回答对问题的针对程度',       icon: '💬' },
    { key: 'consistency',          label: '一致性',         desc: '多轮/多 Agent 结论一致性',   icon: '🔗' },
];

// 流程阶段顺序
const PHASE_ORDER = ['planning', 'retrieving', 'computing', 'judging', 'report'];
const PHASE_LABELS = {
    planning:   '意图解析',
    retrieving: 'GraphRAG 检索',
    computing:  '统计计算',
    judging:    '四维评审',
    report:     '报告生成',
};

// ==================== 状态 ====================
const state = {
    token: localStorage.getItem('ea_token') || '',
    user: null,
    sessionId: genSessionId(),
    messages: [],
    streaming: false,
    abortCtrl: null,
    currentReq: null,   // 当前 SSE 渲染上下文
    done: false,        // 是否已收到 done 事件（区分"正常完成"与"用户手动停止"）
};

// ==================== DOM ====================
const $ = (id) => document.getElementById(id);
const dom = {
    loginView: $('loginView'),
    chatView: $('chatView'),
    loginForm: $('loginForm'),
    loginBtn: $('loginBtn'),
    username: $('username'),
    password: $('password'),
    userChip: $('userChip'),
    logoutBtn: $('logoutBtn'),
    sessionBadge: $('sessionBadge'),
    sidebar: $('sidebar'),
    historyList: $('historyList'),
    newChatBtn: $('newChatBtn'),
    mcpStatus: $('mcpStatus'),
    chatStream: $('chatStream'),
    questionInput: $('questionInput'),
    sendBtn: $('sendBtn'),
    stopBtn: $('stopBtn'),
    suggestList: $('suggestList'),
    judgeBody: $('judgeBody'),
    judgeFoot: $('judgeFoot'),
    overallScore: $('overallScore'),
    judgeVerdict: $('judgeVerdict'),
    judgeCost: $('judgeCost'),
    judgeQaId: $('judgeQaId'),
    toast: $('toast'),
    kbBtn: $('kbBtn'),
    kbMask: $('kbMask'),
    kbDrawer: $('kbDrawer'),
    kbCloseBtn: $('kbCloseBtn'),
    kbDropzone: $('kbDropzone'),
    kbFileInput: $('kbFileInput'),
    kbCategory: $('kbCategory'),
    kbUploadBar: $('kbUploadBar'),
    kbUploadFill: $('kbUploadFill'),
    kbUploadText: $('kbUploadText'),
    kbRefreshBtn: $('kbRefreshBtn'),
    kbList: $('kbList'),
};

// ==================== 工具 ====================
function genSessionId() {
    return 'web-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
}

function toast(msg, type = '') {
    dom.toast.textContent = msg;
    dom.toast.className = 'toast show ' + type;
    dom.toast.hidden = false;
    setTimeout(() => { dom.toast.hidden = true; dom.toast.className = 'toast'; }, 2800);
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function fmtTime(d = new Date()) {
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// ==================== 知识库 ====================
const KB_FILE_ICONS = { pdf: 'PDF', txt: 'TXT', md: 'MD', doc: 'DOC', docx: 'DOC', csv: 'CSV', xlsx: 'XLS', default: 'DOC' };
const KB_INDEX_LABEL = { 0: '待索引', 1: '已索引', 2: '索引中', 3: '索引失败' };

function kbOpen() {
    dom.kbMask.hidden = false;
    dom.kbDrawer.hidden = false;
    requestAnimationFrame(() => {
        dom.kbMask.classList.add('show');
        dom.kbDrawer.classList.add('show');
    });
    kbLoadList();
}

function kbClose() {
    dom.kbMask.classList.remove('show');
    dom.kbDrawer.classList.remove('show');
    setTimeout(() => {
        dom.kbMask.hidden = true;
        dom.kbDrawer.hidden = true;
    }, 280);
}

async function kbLoadList() {
    try {
        const res = await fetch('/api/file/page?pageNo=1&pageSize=100', {
            headers: { 'Authorization': 'Bearer ' + state.token }
        });
        const data = await res.json();
        if (data.code !== 200) { toast('加载文档列表失败: ' + (data.msg || ''), 'error'); return; }
        const records = data.data?.records || [];
        if (records.length === 0) {
            dom.kbList.innerHTML = '<div class="kb-empty">暂无文档，请上传</div>';
            return;
        }
        dom.kbList.innerHTML = records.map(doc => {
            const ext = (doc.fileName || '').split('.').pop()?.toLowerCase() || '';
            const icon = KB_FILE_ICONS[ext] || KB_FILE_ICONS.default;
            const idxLabel = KB_INDEX_LABEL[doc.indexed] || '未知';
            return `<div class="kb-item" data-id="${doc.id}">
                <div class="kb-file-icon">${icon}</div>
                <div class="kb-item-info">
                    <div class="kb-item-name" title="${escapeHtml(doc.fileName)}">${escapeHtml(doc.fileName)}</div>
                    <div class="kb-item-meta">
                        <span>${fmtTime(new Date(doc.createdAt))}</span>
                        <span>${(doc.fileSize / 1024).toFixed(1)}KB</span>
                        <span class="kb-badge idx-${doc.indexed}">${idxLabel}</span>
                        ${doc.category ? `<span>${escapeHtml(doc.category)}</span>` : ''}
                    </div>
                </div>
                <button class="kb-del-btn" data-del="${doc.id}" title="删除">✕</button>
            </div>`;
        }).join('');
    } catch (e) {
        toast('加载文档列表失败: ' + e.message, 'error');
    }
}

async function kbUploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', dom.kbCategory.value.trim() || '');
    dom.kbUploadBar.hidden = false;
    dom.kbUploadText.textContent = `上传中: ${file.name}`;
    dom.kbUploadFill.style.width = '30%';
    try {
        const res = await fetch('/api/file/upload', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + state.token },
            body: formData
        });
        const data = await res.json();
        dom.kbUploadFill.style.width = '100%';
        if (data.code === 200) {
            toast(`上传成功: ${file.name}`, 'success');
            setTimeout(() => { dom.kbUploadBar.hidden = true; dom.kbUploadFill.style.width = '0'; }, 1000);
            await kbLoadList();
        } else {
            toast('上传失败: ' + (data.msg || ''), 'error');
            dom.kbUploadBar.hidden = true;
        }
    } catch (e) {
        toast('上传失败: ' + e.message, 'error');
        dom.kbUploadBar.hidden = true;
    }
}

async function kbDelete(docId) {
    if (!confirm('确认删除该文档？关联的 GraphRAG 索引将一并移除。')) return;
    try {
        const res = await fetch(`/api/file/${docId}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + state.token }
        });
        const data = await res.json();
        if (data.code === 200) {
            toast('删除成功', 'success');
            await kbLoadList();
        } else {
            toast('删除失败: ' + (data.msg || ''), 'error');
        }
    } catch (e) {
        toast('删除失败: ' + e.message, 'error');
    }
}

function fmtDate(iso) {
    if (!iso) return '';
    const d = new(iso.replace(' ', 'T') + (iso.includes('T') ? '' : 'Z'));
    return isNaN(d) ? iso.slice(5, 16) : `${d.getMonth()+1}/${d.getDate()} ${fmtTime(d)}`;
}

function authHeaders(json = true) {
    const h = { 'Authorization': 'Bearer ' + state.token };
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

async function api(url, opts = {}) {
    const res = await fetch(url, {
        ...opts,
        headers: { ...authHeaders(opts.json !== false), ...(opts.headers || {}) },
    });
    if (res.status === 401) { toast('登录已过期，请重新登录', 'error'); logout(); throw new Error('401'); }
    return res;
}

// ==================== 认证 ====================
async function login(e) {
    e.preventDefault();
    const username = dom.username.value.trim();
    const password = dom.password.value;
    if (!username || !password) { toast('请输入账号密码', 'error'); return; }

    dom.loginBtn.disabled = true;
    dom.loginBtn.querySelector('.btn-text').textContent = '登录中...';
    try {
        const res = await fetch(API.LOGIN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const json = await res.json();
        if (res.ok && json.code === 200 && json.data?.token) {
            state.token = json.data.token;
            state.user = json.data;
            localStorage.setItem('ea_token', state.token);
            toast('登录成功', 'success');
            enterChat();
        } else {
            toast(json.message || '登录失败', 'error');
        }
    } catch (err) {
        toast('网络异常：' + err.message, 'error');
    } finally {
        dom.loginBtn.disabled = false;
        dom.loginBtn.querySelector('.btn-text').textContent = '登 录';
    }
}

function logout() {
    state.token = '';
    state.user = null;
    localStorage.removeItem('ea_token');
    dom.loginView.hidden = false;
    dom.chatView.hidden = true;
    dom.loginForm.reset();
    dom.password.value = '';
}

async function fetchUser() {
    try {
        const res = await api(API.ME);
        const json = await res.json();
        if (json.code === 200) {
            state.user = json.data;
            return true;
        }
    } catch (e) { /* ignore */ }
    return false;
}

async function enterChat() {
    dom.loginView.hidden = true;
    dom.chatView.hidden = false;
    const u = state.user || {};
    const name = u.realName || u.username || '用户';
    dom.userChip.textContent = '👤 ' + name;
    dom.sessionBadge.textContent = '会话: ' + state.sessionId.slice(-8);
    dom.sendBtn.disabled = false;
    dom.questionInput.focus();
    loadHistory();
    checkMcp();
}

// ==================== MCP 健康检查 ====================
async function checkMcp() {
    dom.mcpStatus.innerHTML = '<span class="dot dot-gray"></span> MCP 工具检测中';
    try {
        const res = await api(API.MCP_TOOLS);
        const json = await res.json();
        if (json.code === 200) {
            const tools = json.data || [];
            if (tools.length) {
                dom.mcpStatus.innerHTML = `<span class="dot dot-green"></span> MCP 正常 · ${tools.length} 个工具`;
            } else {
                dom.mcpStatus.innerHTML = '<span class="dot dot-amber"></span> MCP 未发现工具';
            }
        } else {
            dom.mcpStatus.innerHTML = '<span class="dot dot-amber"></span> MCP 异常';
        }
    } catch (e) {
        dom.mcpStatus.innerHTML = '<span class="dot dot-amber"></span> MCP 不可达';
    }
}

// ==================== 历史 ====================
async function loadHistory() {
    try {
        const res = await api(API.HISTORY + '?pageNo=1&pageSize=20');
        const json = await res.json();
        if (json.code === 200 && json.data?.records) {
            renderHistory(json.data.records);
        } else {
            dom.historyList.innerHTML = '<div class="history-empty">暂无历史记录</div>';
        }
    } catch (e) {
        dom.historyList.innerHTML = '<div class="history-empty">历史加载失败</div>';
    }
}

function renderHistory(records) {
    if (!records.length) {
        dom.historyList.innerHTML = '<div class="history-empty">暂无历史记录</div>';
        return;
    }
    dom.historyList.innerHTML = records.map((r, i) => `
        <div class="history-item ${i === 0 ? 'active' : ''}" data-id="${r.id}" title="${escapeHtml(r.question)}">
            <div class="hi-q">${escapeHtml(r.question)}</div>
            <div class="hi-time">${fmtDate(r.createTime)}</div>
        </div>
    `).join('');
}

// ==================== 对话渲染 ====================
function clearWelcome() {
    const w = dom.chatStream.querySelector('.welcome');
    if (w) w.remove();
}

function appendUserMsg(text) {
    clearWelcome();
    const el = document.createElement('div');
    el.className = 'msg msg-user';
    el.innerHTML = `
        <div class="msg-avatar">我</div>
        <div class="msg-bubble">
            <div class="msg-content">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
            <div class="msg-time">${fmtTime()}</div>
        </div>`;
    dom.chatStream.appendChild(el);
    scrollToBottom();
}

function appendBotMsg() {
    clearWelcome();
    const el = document.createElement('div');
    el.className = 'msg msg-bot';
    el.innerHTML = `
        <div class="msg-avatar">AI</div>
        <div class="msg-bubble">
            <div class="phase-flow" style="display:none"></div>
            <div class="msg-content" style="display:none"></div>
            <div class="msg-time">${fmtTime()}</div>
        </div>`;
    dom.chatStream.appendChild(el);
    scrollToBottom();
    return {
        bubble: el,
        flow: el.querySelector('.phase-flow'),
        content: el.querySelector('.msg-content'),
    };
}

function scrollToBottom() {
    dom.chatStream.scrollTop = dom.chatStream.scrollHeight;
}

// ==================== 流程阶段渲染 ====================
function renderPhaseFlow(el) {
    el.style.display = 'flex';
    el.innerHTML = `<span class="pf-label">流程</span>` + PHASE_ORDER.map(p => `
        <span class="phase-chip" data-phase="${p}">
            <span class="pc-dot"></span>${PHASE_LABELS[p]}
        </span>`).join('');
}

function setPhase(el, phase, status) { // status: active | done
    const chips = el.querySelectorAll('.phase-chip');
    chips.forEach(c => {
        if (c.dataset.phase === phase) {
            c.classList.remove('active', 'done');
            c.classList.add(status);
        }
    });
    // 之前的阶段标记为 done
    const idx = PHASE_ORDER.indexOf(phase);
    chips.forEach(c => {
        const ci = PHASE_ORDER.indexOf(c.dataset.phase);
        if (ci < idx && !c.classList.contains('done')) {
            c.classList.remove('active');
            c.classList.add('done');
        }
    });
}

// ==================== Judge 四维面板 ====================
function renderJudgePanel(data) {
    const scores = extractScores(data);
    let html = '';
    for (const dim of JUDGE_DIMS) {
        const val = scores[dim.key];
        const pct = (val == null) ? 0 : Math.round(val * 100);
        const level = pct >= 70 ? 'good' : (pct >= 40 ? 'mid' : 'bad');
        const scoreText = (val == null) ? '—' : (typeof val === 'number' ? val.toFixed(2) : val);
        html += `
        <div class="judge-dim">
            <div class="judge-dim-head">
                <span class="judge-dim-name"><span class="jd-icon">${dim.icon}</span>${dim.label}</span>
                <span class="judge-dim-score">${scoreText}</span>
            </div>
            <div class="judge-bar"><div class="judge-bar-fill" data-level="${level}" data-pct="${pct}"></div></div>
            <div class="judge-dim-desc">${dim.desc}</div>
        </div>`;
    }
    dom.judgeBody.innerHTML = html;
    // 触发动画
    requestAnimationFrame(() => {
        dom.judgeBody.querySelectorAll('.judge-bar-fill').forEach(b => {
            b.style.width = b.dataset.pct + '%';
        });
    });
}

function extractScores(data) {
    // 兼容多种字段命名
    const result = {};
    if (!data || typeof data !== 'object') return result;
    for (const dim of JUDGE_DIMS) {
        const k = dim.key;
        result[k] = data[k] ?? data[camel(k)] ?? data[k.replace(/_/g, '')] ?? null;
    }
    return result;
}

function camel(s) { return s.replace(/_([a-z])/g, (_, c) => c.toUpperCase()); }

function resetJudgePanel() {
    dom.judgeBody.innerHTML = '<div class="judge-empty"><p>提交分析后，<br/>四维评审将在此实时展示</p></div>';
    dom.judgeFoot.hidden = true;
}

function showJudgeMeta(meta) {
    dom.judgeFoot.hidden = false;
    if (meta.overallScore != null) {
        const pct = Math.round(meta.overallScore * 100);
        dom.overallScore.textContent = pct + ' / 100';
    }
    if (meta.passed != null) {
        dom.judgeVerdict.textContent = meta.passed ? '✓ 通过' : '✗ 不通过';
        dom.judgeVerdict.className = 'meta-val ' + (meta.passed ? 'verdict-pass' : 'verdict-fail');
    }
    if (meta.costMs != null) dom.judgeCost.textContent = meta.costMs;
    if (meta.qaId != null) dom.judgeQaId.textContent = meta.qaId;
}

// ==================== 打字机效果 ====================
function startTypewriter(contentEl) {
    // contentEl 已有完整文本，重新做打字机
    return {
        el: contentEl,
        cursor: null,
        append(chunk) {
            // 直接追加文本块（report 事件已是增量），打字机逐字符显示
            this._type(chunk);
        },
        _full: '',
        _idx: 0,
        _timer: null,
        _type(chunk) {
            this._full += chunk;
            if (this._timer) return; // 已在打字
            this._tick();
        },
        _tick() {
            const remain = this._full.slice(this._idx);
            if (!remain) { this._stop(); return; }
            // 每次推进若干字符（中文按词更快）
            const step = /[\u4e00-\u9fa5]/.test(remain[0]) ? 2 : 4;
            this._idx += Math.min(step, remain.length);
            this._render();
            this._timer = setTimeout(() => this._tick(), 16);
        },
        _render() {
            this.el.innerHTML = renderMarkdown(this._full.slice(0, this._idx)) + '<span class="typing-cursor"></span>';
            scrollToBottom();
        },
        _stop() {
            this._timer = null;
            this.el.innerHTML = renderMarkdown(this._full);
            scrollToBottom();
        },
        finish() {
            if (this._timer) { clearTimeout(this._timer); this._timer = null; }
            this._idx = this._full.length;
            this.el.innerHTML = renderMarkdown(this._full);
            scrollToBottom();
        }
    };
}

// 简易 Markdown 渲染
function renderMarkdown(text) {
    let html = escapeHtml(text);
    // 代码块
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
        `<pre><code>${code.replace(/&amp;nbsp;/g, ' ').trim()}</code></pre>`);
    // 行内代码
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    // 粗体
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // 换行转段落
    const paras = html.split(/\n{2,}/).map(p => '<p>' + p.replace(/\n/g, '<br>') + '</p>');
    return paras.join('');
}

// ==================== SSE 流式分析 ====================
async function sendQuestion() {
    const question = dom.questionInput.value.trim();
    if (!question) { toast('请输入问题', 'error'); return; }
    if (state.streaming) { toast('正在分析中，请稍候', 'error'); return; }

    appendUserMsg(question);
    dom.questionInput.value = '';          // 发送后清空输入框
    dom.questionInput.style.height = '';   // 重置 textarea 自适应高度
    const bot = appendBotMsg();
    renderPhaseFlow(bot.flow);
    bot.content.style.display = 'block';
    bot.content.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

    resetJudgePanel();
    setStreaming(true);

    const tw = startTypewriter(bot.content);
    state.currentReq = { tw, flow: bot.flow, content: bot.content, reportStarted: false };

    state.abortCtrl = new AbortController();
    state.done = false;
    try {
        await streamSse(question, state.sessionId, state.abortCtrl.signal, (event, data) => {
            handleSseEvent(event, data, state.currentReq);
        });
    } catch (err) {
        if (err.name === 'AbortError') {
            tw.finish();
            // 收到 done 后主动 abort 关闭流，不算"用户手动停止"，不提示
            if (!state.done) {
                appendNotice(bot.content, '⏹ 已停止生成', 'warning');
            }
        } else {
            bot.content.style.display = 'block';
            bot.content.innerHTML += `<p style="color:var(--danger)">⚠ 流式连接异常：${escapeHtml(err.message)}</p>`;
        }
    } finally {
        tw.finish();
        setStreaming(false);
        state.currentReq = null;
        state.abortCtrl = null;
        loadHistory(); // 刷新历史
    }
}

function appendNotice(contentEl, text, type) {
    const p = document.createElement('div');
    p.className = 'cache-hit';
    p.textContent = text;
    contentEl.parentElement.insertBefore(p, contentEl.parentElement.querySelector('.msg-time'));
}

// SSE 流解析（fetch + ReadableStream，支持 POST）
async function streamSse(question, sessionId, signal, onEvent) {
    const res = await fetch(API.STREAM, {
        method: 'POST',
        headers: { ...authHeaders(), 'Accept': 'text/event-stream' },
        body: JSON.stringify({ question, sessionId }),
        signal,
    });
    if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { const j = await res.json(); msg = j.message || msg; } catch (e) {}
        throw new Error(msg);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // 按空行分割事件
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const parsed = parseSseBlock(raw);
            if (parsed) onEvent(parsed.event, parsed.data);
        }
    }
    // 处理剩余
    if (buffer.trim()) {
        const parsed = parseSseBlock(buffer);
        if (parsed) onEvent(parsed.event, parsed.data);
    }
}

function parseSseBlock(raw) {
    const lines = raw.split('\n');
    let event = 'message';
    const dataLines = [];
    for (const line of lines) {
        if (line.startsWith('event:')) {
            event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).replace(/^ /, ''));
        } else if (line.startsWith(':')) {
            // 注释/心跳，忽略
        }
    }
    if (dataLines.length === 0) return null;
    return { event, data: dataLines.join('\n') };
}

// 处理单个 SSE 事件
function handleSseEvent(event, data, req) {
    let json = null;
    try { json = JSON.parse(data); } catch (e) { /* 非 JSON，按文本处理 */ }

    switch (event) {
        case 'planning': {
            setPhase(req.flow, 'planning', 'active');
            req.content.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>' +
                (json?.message ? `<span style="font-size:13px;color:var(--text-2);margin-left:8px">${escapeHtml(json.message)}</span>` : '');
            break;
        }
        case 'retrieving': {
            setPhase(req.flow, 'retrieving', 'active');
            const srcCount = json?.sources ?? json?.sourceCount;
            req.content.innerHTML = (srcCount ? `已检索 ${srcCount} 条相关知识片段` : 'GraphRAG 检索完成') +
                '<div class="loading-dots" style="display:inline-flex;margin-left:6px"><span></span><span></span><span></span></div>';
            break;
        }
        case 'computing': {
            setPhase(req.flow, 'computing', 'active');
            req.content.innerHTML = '正在执行 SQL/统计计算' +
                '<div class="loading-dots" style="display:inline-flex;margin-left:6px"><span></span><span></span><span></span></div>';
            break;
        }
        case 'judging': {
            setPhase(req.flow, 'judging', 'active');
            renderJudgePanel(json || {});
            break;
        }
        case 'report': {
            if (!req.reportStarted) {
                req.reportStarted = true;
                setPhase(req.flow, 'report', 'active');
                req.content.innerHTML = '';
                req.tw._full = '';
                req.tw._idx = 0;
            }
            // report data 可能是纯文本块或 {chunk: "..."}
            const chunk = (json?.chunk || json?.text || (typeof json === 'string' ? json : '') || data);
            if (chunk) req.tw.append(chunk);
            break;
        }
        case 'cacheHit': {
            const q = req.content.parentElement.querySelector('.msg-time');
            const badge = document.createElement('div');
            badge.className = 'cache-hit';
            badge.textContent = '⚡ 缓存命中，秒级返回';
            req.content.parentElement.insertBefore(badge, q);
            break;
        }
        case 'done': {
            PHASE_ORDER.forEach(p => setPhase(req.flow, p, 'done'));
            if (json) {
                showJudgeMeta({
                    overallScore: json.overallScore ?? json.score,
                    passed: json.passed ?? json.judgePassed,
                    costMs: json.costMs ?? json.elapsed,
                    qaId: json.qaId ?? json.id,
                });
            }
            // 业务流已结束：主动 abort 关闭 SSE 连接，避免后端心跳 `:hb` 导致 reader 永不 done
            state.done = true;
            if (state.abortCtrl) {
                try { state.abortCtrl.abort(); } catch (e) { /* 已关闭 */ }
            }
            break;
        }
        case 'error': {
            req.content.style.display = 'block';
            req.content.innerHTML += `<p style="color:var(--danger)">⚠ ${escapeHtml(json?.message || data || '分析失败')}</p>`;
            break;
        }
        default: {
            // 其它事件忽略
        }
    }
    scrollToBottom();
}

function stopStream() {
    if (state.abortCtrl) state.abortCtrl.abort();
}

function setStreaming(on) {
    state.streaming = on;
    dom.sendBtn.hidden = on;
    dom.stopBtn.hidden = !on;
    dom.questionInput.disabled = false;
}

// ==================== 事件绑定 ====================
function bindEvents() {
    dom.loginForm.addEventListener('submit', login);
    dom.logoutBtn.addEventListener('click', logout);
    dom.newChatBtn.addEventListener('click', () => {
        state.sessionId = genSessionId();
        dom.sessionBadge.textContent = '会话: ' + state.sessionId.slice(-8);
        dom.chatStream.innerHTML = '';
        resetJudgePanel();
        toast('已开启新会话', 'success');
    });
    dom.sendBtn.addEventListener('click', sendQuestion);
    dom.stopBtn.addEventListener('click', stopStream);

    // 输入框
    dom.questionInput.addEventListener('input', () => {
        const v = dom.questionInput.value;
        dom.questionInput.style.height = 'auto';
        dom.questionInput.style.height = Math.min(dom.questionInput.scrollHeight, 140) + 'px';
    });
    dom.questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuestion();
        }
    });

    // 建议词
    dom.suggestList.addEventListener('click', (e) => {
        const chip = e.target.closest('.suggest-chip');
        if (chip) {
            dom.questionInput.value = chip.dataset.q;
            dom.questionInput.dispatchEvent(new Event('input'));
            sendQuestion();
        }
    });

    // 历史点击
    dom.historyList.addEventListener('click', (e) => {
        const item = e.target.closest('.history-item');
        if (item) {
            dom.historyList.querySelectorAll('.history-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        }
    });

    // 知识库抽屉
    dom.kbBtn.addEventListener('click', kbOpen);
    dom.kbCloseBtn.addEventListener('click', kbClose);
    dom.kbMask.addEventListener('click', kbClose);
    dom.kbRefreshBtn.addEventListener('click', kbLoadList);
    dom.kbDropzone.addEventListener('click', () => dom.kbFileInput.click());
    dom.kbFileInput.addEventListener('change', async (e) => {
        const files = Array.from(e.target.files || []);
        for (const f of files) { await kbUploadFile(f); }
        e.target.value = '';
    });
    dom.kbDropzone.addEventListener('dragover', (e) => { e.preventDefault(); dom.kbDropzone.classList.add('dragover'); });
    dom.kbDropzone.addEventListener('dragleave', () => dom.kbDropzone.classList.remove('dragover'));
    dom.kbDropzone.addEventListener('drop', async (e) => {
        e.preventDefault();
        dom.kbDropzone.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files || []);
        for (const f of files) { await kbUploadFile(f); }
    });
    dom.kbList.addEventListener('click', (e) => {
        const delBtn = e.target.closest('[data-del]');
        if (delBtn) { kbDelete(delBtn.dataset.del); }
    });
}

// ==================== 初始化 ====================
async function init() {
    bindEvents();
    if (state.token) {
        const ok = await fetchUser();
        if (ok) { enterChat(); return; }
        logout();
    }
    dom.loginView.hidden = false;
    dom.chatView.hidden = true;
    dom.username.focus();
}

document.addEventListener('DOMContentLoaded', init);

})();
