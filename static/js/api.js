/**
 * API Client - 封装所有后端 API 调用
 */

const API_BASE = '';  // 相对路径，同源部署

class APIClient {
    /**
     * 获取账号列表
     */
    async getAccounts() {
        const response = await fetch(`${API_BASE}/admin/accounts`);
        if (!response.ok) {
            throw new Error(`Failed to fetch accounts: ${response.statusText}`);
        }
        return await response.json();
    }

    /**
     * 添加账号
     */
    async addAccount(accountData) {
        const response = await fetch(`${API_BASE}/admin/accounts`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(accountData),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to add account');
        }

        return await response.json();
    }

    /**
     * 删除账号
     */
    async deleteAccount(email) {
        const response = await fetch(`${API_BASE}/admin/accounts/${encodeURIComponent(email)}`, {
            method: 'DELETE',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete account');
        }

        return await response.json();
    }

    /**
     * 清除账号冷却状态
     */
    async clearCooldown(email) {
        const response = await fetch(`${API_BASE}/admin/accounts/${encodeURIComponent(email)}/clear-cooldown`, {
            method: 'POST',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to clear cooldown');
        }

        return await response.json();
    }

    /**
     * 获取统计信息
     */
    async getStats() {
        const response = await fetch(`${API_BASE}/admin/stats`);
        if (!response.ok) {
            throw new Error(`Failed to fetch stats: ${response.statusText}`);
        }
        return await response.json();
    }
}

// 全局 API 客户端实例
const api = new APIClient();
