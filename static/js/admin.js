/**
 * Admin UI Main Controller - 主控制器
 */

// 当前激活的 Tab
let currentTab = 'dashboard';

// 刷新间隔（毫秒）
const REFRESH_INTERVAL = 5 * 60 * 1000;
let refreshTimer = null;

/**
 * 页面加载完成后初始化
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('Admin UI initialized');

    // 初始化图表
    chartsManager.init();

    // 连接 SSE
    sseManager.connect();

    // 加载初始数据
    loadDashboard();
    loadAccounts();

    // 设置定时刷新
    startAutoRefresh();

    // 设置表单提交处理
    setupFormHandlers();

    // 设置默认 Tab 样式
    updateTabStyles();
});

/**
 * 切换 Tab
 */
function switchTab(tabName) {
    // 隐藏所有 Tab 内容
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // 显示选中的 Tab
    const selectedTab = document.getElementById(`${tabName}-tab`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    currentTab = tabName;
    updateTabStyles();

    // 加载对应数据
    if (tabName === 'dashboard') {
        loadDashboard();
    } else if (tabName === 'accounts') {
        loadAccounts();
    }
}

/**
 * 更新 Tab 按钮样式
 */
function updateTabStyles() {
    document.querySelectorAll('.tab-button').forEach(button => {
        const tabName = button.dataset.tab;
        if (tabName === currentTab) {
            button.className = 'tab-button whitespace-nowrap py-4 px-1 border-b-2 border-blue-500 font-medium text-sm text-blue-600';
        } else {
            button.className = 'tab-button whitespace-nowrap py-4 px-1 border-b-2 border-transparent font-medium text-sm text-gray-500 hover:text-gray-700 hover:border-gray-300';
        }
    });
}

/**
 * 加载 Dashboard 数据
 */
async function loadDashboard() {
    try {
        const stats = await api.getStats();

        // 更新统计卡片
        document.getElementById('stat-total').textContent = stats.total_accounts;
        document.getElementById('stat-active').textContent = stats.active_accounts;
        document.getElementById('stat-cooldown').textContent = stats.cooldown_accounts;
        document.getElementById('stat-expired').textContent = stats.expired_accounts;

        // 更新图表
        chartsManager.updateCharts(stats);

    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showNotification('加载 Dashboard 失败: ' + error.message, 'error');
    }
}

/**
 * 加载账号列表
 */
async function loadAccounts() {
    try {
        const accounts = await api.getAccounts();
        updateCookieExpiryAlert(accounts);
        renderAccountsTable(accounts);
    } catch (error) {
        console.error('Failed to load accounts:', error);
        showNotification('加载账号列表失败: ' + error.message, 'error');
    }
}

function updateCookieExpiryAlert(accounts) {
    const alertBox = document.getElementById('cookie-expiry-alert');
    const alertText = document.getElementById('cookie-expiry-alert-text');
    if (!alertBox || !alertText) {
        return;
    }

    const authIssues = accounts.filter(account =>
        account.status === 'cooldown_401' || account.status === 'cooldown_403'
    );

    if (authIssues.length === 0) {
        alertBox.classList.add('hidden');
        alertText.textContent = '';
        return;
    }

    const emails = authIssues.map(account => account.email).join('，');
    alertText.textContent = `检测到 ${authIssues.length} 个账号认证失败（401/403），请刷新 Cookie：${emails}`;
    alertBox.classList.remove('hidden');
}

function getTokenExpiryDisplay(expiresAt) {
    if (!expiresAt) {
        return {
            timeLabel: '未设置',
            remainingLabel: '—',
            className: 'text-gray-500'
        };
    }

    const expiryDate = new Date(expiresAt);
    if (Number.isNaN(expiryDate.getTime())) {
        return {
            timeLabel: '无效时间',
            remainingLabel: '—',
            className: 'text-red-600 font-semibold'
        };
    }

    const now = Date.now();
    const diffMs = expiryDate.getTime() - now;
    const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
    const remainingLabel = diffMs <= 0 ? '已过期' : `${diffHours} 小时`;

    let className = 'text-gray-900';
    if (diffMs <= 0 || diffHours <= 6) {
        className = 'text-red-600 font-semibold';
    } else if (diffHours <= 24) {
        className = 'text-yellow-600';
    }

    return {
        timeLabel: expiryDate.toLocaleString('zh-CN'),
        remainingLabel,
        className
    };
}

/**
 * 渲染账号列表表格
 */
function renderAccountsTable(accounts) {
    const tbody = document.getElementById('accounts-table-body');
    tbody.innerHTML = '';

    if (accounts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-8 text-center text-gray-500">
                    暂无账号，点击右上角"添加账号"按钮添加
                </td>
            </tr>
        `;
        return;
    }

    accounts.forEach(account => {
        const row = createAccountRow(account);
        tbody.appendChild(row);
    });
}

/**
 * 创建账号行
 */
function createAccountRow(account) {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-gray-50';

    // 状态标签
    let statusBadge = '';
    if (account.status === 'active') {
        statusBadge = '<span class="status-badge status-active">可用</span>';
    } else if (account.status === 'cooldown_401') {
        statusBadge = '<span class="status-badge status-cooldown">认证失败(401)</span>';
    } else if (account.status === 'cooldown_403') {
        statusBadge = '<span class="status-badge status-cooldown">认证失败(403)</span>';
    } else if (account.status === 'cooldown_429') {
        statusBadge = '<span class="status-badge status-cooldown">限流冷却</span>';
    } else if (account.status === 'expiring_soon') {
        statusBadge = '<span class="status-badge status-cooldown">即将过期</span>';
    } else if (account.status === 'expired') {
        statusBadge = '<span class="status-badge status-expired">已过期</span>';
    } else if (account.status === 'error') {
        statusBadge = '<span class="status-badge status-expired">异常</span>';
    } else {
        statusBadge = `<span class="status-badge status-cooldown">${escapeHtml(account.status)}</span>`;
    }

    // 最后使用时间
    const lastUsed = account.last_used_at
        ? new Date(account.last_used_at).toLocaleString('zh-CN')
        : '未使用';

    const tokenExpiry = getTokenExpiryDisplay(account.expires_at);

    tr.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
            ${escapeHtml(account.email)}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm">
            ${statusBadge}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm ${tokenExpiry.className}">
            <div>${tokenExpiry.timeLabel}</div>
            <div class="text-xs text-gray-500">剩余 ${tokenExpiry.remainingLabel}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
            ${account.total_requests}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm ${account.failed_requests > 0 ? 'text-red-600' : 'text-gray-900'}">
            ${account.failed_requests}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
            ${lastUsed}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm space-x-3">
            ${(account.status || '').startsWith('cooldown')
                ? `<button onclick="clearCooldownConfirm('${escapeHtml(account.email)}')"
                        class="text-blue-600 hover:text-blue-900">
                        🔓 清除冷却
                   </button>`
                : ''}
            <button onclick="deleteAccountConfirm('${escapeHtml(account.email)}')"
                    class="text-red-600 hover:text-red-900">
                🗑️ 删除
            </button>
        </td>
    `;

    return tr;
}

/**
 * 清除账号冷却状态
 */
async function clearCooldownConfirm(email) {
    if (!confirm(`确定要清除账号 ${email} 的冷却状态吗？`)) {
        return;
    }

    try {
        await api.clearCooldown(email);
        showNotification(`已清除冷却：${email}`, 'success');
        await loadAccounts();
    } catch (error) {
        console.error('Failed to clear cooldown:', error);
        showNotification('清除冷却失败: ' + error.message, 'error');
    }
}

/**
 * 显示添加账号模态框
 */
function showAddAccountModal() {
    document.getElementById('add-account-modal').classList.remove('hidden');
}

/**
 * 隐藏添加账号模态框
 */
function hideAddAccountModal() {
    document.getElementById('add-account-modal').classList.add('hidden');
    document.getElementById('add-account-form').reset();
    const preview = document.getElementById('cookie-expiry-preview');
    if (preview) {
        preview.textContent = '预计 cookie 过期时间（12小时）：未计算';
    }
}

/**
 * 设置表单处理器
 */
function setupFormHandlers() {
    const form = document.getElementById('add-account-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await handleAddAccount(form);
    });
}

/**
 * 处理添加账号
 */
async function handleAddAccount(form) {
    const formData = new FormData(form);
    const accountData = {
        email: formData.get('email'),
        team_id: formData.get('team_id'),
        secure_c_ses: formData.get('secure_c_ses'),
        host_c_oses: formData.get('host_c_oses'),
        csesidx: formData.get('csesidx'),
        user_agent: formData.get('user_agent'),
    };
    const expiresAt = formData.get('expires_at');
    const createdAt = formData.get('created_at');
    if (expiresAt) {
        accountData.expires_at = expiresAt;
    }
    if (createdAt) {
        accountData.created_at = createdAt;
    }

    try {
        await api.addAccount(accountData);
        showNotification('账号添加成功', 'success');
        hideAddAccountModal();
        loadAccounts();
        loadDashboard();
    } catch (error) {
        console.error('Failed to add account:', error);
        showNotification('添加账号失败: ' + error.message, 'error');
    }
}

function applyPluginJson() {
    const input = document.getElementById('plugin-json-input');
    if (!input || !input.value.trim()) {
        showNotification('请先粘贴插件 JSON', 'warning');
        return;
    }

    let payload;
    try {
        payload = JSON.parse(input.value.trim());
    } catch (error) {
        showNotification('JSON 解析失败，请检查格式', 'error');
        return;
    }

    const form = document.getElementById('add-account-form');
    form.querySelector('[name="team_id"]').value = payload.team_id || '';
    form.querySelector('[name="secure_c_ses"]').value = payload.secure_c_ses || '';
    form.querySelector('[name="host_c_oses"]').value = payload.host_c_oses || '';
    form.querySelector('[name="csesidx"]').value = payload.csesidx || '';
    form.querySelector('[name="user_agent"]').value = payload.user_agent || '';

    const now = new Date();
    const cookieExpiry = new Date(now.getTime() + 12 * 60 * 60 * 1000);
    const expiresAtInput = document.getElementById('expires-at-input');
    const createdAtInput = document.getElementById('created-at-input');
    if (expiresAtInput) {
        expiresAtInput.value = cookieExpiry.toISOString();
    }
    if (createdAtInput) {
        createdAtInput.value = now.toISOString();
    }

    const preview = document.getElementById('cookie-expiry-preview');
    if (preview) {
        preview.textContent = `预计 cookie 过期时间（12小时）：${cookieExpiry.toLocaleString('zh-CN')}`;
    }

    if (!form.querySelector('[name="email"]').value) {
        showNotification('请补充账号邮箱', 'warning');
    }
}

/**
 * 删除账号确认
 */
function deleteAccountConfirm(email) {
    if (confirm(`确定要删除账号 ${email} 吗？此操作不可恢复。`)) {
        deleteAccountHandler(email);
    }
}

/**
 * 处理删除账号
 */
async function deleteAccountHandler(email) {
    try {
        await api.deleteAccount(email);
        showNotification('账号删除成功', 'success');
        loadAccounts();
        loadDashboard();
    } catch (error) {
        console.error('Failed to delete account:', error);
        showNotification('删除账号失败: ' + error.message, 'error');
    }
}

/**
 * 日志级别过滤
 */
function filterLogs() {
    const level = document.getElementById('log-level-filter').value;
    const logs = document.querySelectorAll('.log-entry');

    logs.forEach(log => {
        if (level === 'all' || log.dataset.level === level) {
            log.style.display = '';
        } else {
            log.style.display = 'none';
        }
    });
}

/**
 * 清空日志
 */
function clearLogs() {
    if (confirm('确定要清空所有日志吗？')) {
        document.getElementById('logs-container').innerHTML = '';
    }
}

/**
 * 开始自动刷新
 */
function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(() => {
        if (currentTab === 'dashboard') {
            loadDashboard();
        } else if (currentTab === 'accounts') {
            loadAccounts();
        }
    }, REFRESH_INTERVAL);
}

/**
 * 停止自动刷新
 */
function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    // 简单的 alert 通知，可以后续改进为 toast
    if (type === 'error') {
        alert('❌ ' + message);
    } else if (type === 'success') {
        alert('✅ ' + message);
    } else if (type === 'warning') {
        alert('⚠️ ' + message);
    } else {
        alert('ℹ️ ' + message);
    }
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 页面卸载前清理
 */
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
    sseManager.disconnect();
});
