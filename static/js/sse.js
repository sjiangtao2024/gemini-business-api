/**
 * SSE Connection Manager - 管理 Server-Sent Events 连接
 */

class SSEManager {
    constructor() {
        this.eventSource = null;
        this.reconnectInterval = 3000;
        this.reconnectTimer = null;
        this.isConnected = false;
    }

    /**
     * 连接到日志流
     */
    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.eventSource = new EventSource('/admin/logs/stream');

        this.eventSource.addEventListener('log', (event) => {
            try {
                const logData = JSON.parse(event.data);
                this.handleLogMessage(logData);
            } catch (error) {
                console.error('Failed to parse log data:', error);
            }
        });

        this.eventSource.addEventListener('ping', () => {
            // 心跳包，保持连接活跃
            this.updateConnectionStatus(true);
        });

        this.eventSource.onopen = () => {
            console.log('SSE connected');
            this.isConnected = true;
            this.updateConnectionStatus(true);
            this.clearReconnectTimer();
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.eventSource.close();
            this.scheduleReconnect();
        };
    }

    /**
     * 断开连接
     */
    disconnect() {
        this.clearReconnectTimer();
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.updateConnectionStatus(false);
    }

    /**
     * 处理日志消息
     */
    handleLogMessage(logData) {
        const logsContainer = document.getElementById('logs-container');
        const logEntry = this.createLogEntry(logData);
        logsContainer.appendChild(logEntry);

        // 自动滚动到底部
        logsContainer.scrollTop = logsContainer.scrollHeight;

        // 限制日志数量（避免 DOM 过大）
        const maxLogs = 500;
        while (logsContainer.children.length > maxLogs) {
            logsContainer.removeChild(logsContainer.firstChild);
        }
    }

    /**
     * 创建日志条目 DOM 元素
     */
    createLogEntry(logData) {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${logData.level.toLowerCase()}`;
        entry.dataset.level = logData.level;

        const timestamp = new Date(logData.timestamp).toLocaleTimeString('zh-CN');

        entry.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="text-xs text-gray-500 font-mono">${timestamp}</span>
                <span class="text-xs font-semibold">${logData.level}</span>
                <span class="text-xs text-gray-600 flex-1">${this.escapeHtml(logData.message)}</span>
            </div>
        `;

        return entry;
    }

    /**
     * 更新连接状态显示
     */
    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (connected) {
            statusElement.textContent = '🟢 已连接';
            statusElement.className = 'text-sm text-green-600';
        } else {
            statusElement.textContent = '🔴 未连接';
            statusElement.className = 'text-sm text-red-600';
        }
    }

    /**
     * 安排重连
     */
    scheduleReconnect() {
        this.clearReconnectTimer();
        this.reconnectTimer = setTimeout(() => {
            console.log('Attempting to reconnect...');
            this.connect();
        }, this.reconnectInterval);
    }

    /**
     * 清除重连定时器
     */
    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    /**
     * HTML 转义
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// 全局 SSE 管理器实例
const sseManager = new SSEManager();
