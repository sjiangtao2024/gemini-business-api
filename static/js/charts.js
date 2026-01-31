/**
 * Charts Manager - 使用 Chart.js 管理图表
 */

class ChartsManager {
    constructor() {
        this.statusChart = null;
        this.successChart = null;
    }

    /**
     * 初始化所有图表
     */
    init() {
        this.initStatusChart();
        this.initSuccessChart();
    }

    /**
     * 初始化账号状态分布图（饼图）
     */
    initStatusChart() {
        const ctx = document.getElementById('statusChart');
        if (!ctx) return;

        this.statusChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['可用', '冷却中', '已过期'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [
                        'rgb(34, 197, 94)',   // green-500
                        'rgb(234, 179, 8)',   // yellow-500
                        'rgb(239, 68, 68)',   // red-500
                    ],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                    }
                }
            }
        });
    }

    /**
     * 初始化请求成功率图（饼图）
     */
    initSuccessChart() {
        const ctx = document.getElementById('successChart');
        if (!ctx) return;

        this.successChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['成功', '失败'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: [
                        'rgb(34, 197, 94)',   // green-500
                        'rgb(239, 68, 68)',   // red-500
                    ],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? ((value / total) * 100).toFixed(2) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * 更新状态分布图
     */
    updateStatusChart(stats) {
        if (!this.statusChart) return;

        this.statusChart.data.datasets[0].data = [
            stats.active_accounts,
            stats.cooldown_accounts,
            stats.expired_accounts
        ];
        this.statusChart.update();
    }

    /**
     * 更新成功率图
     */
    updateSuccessChart(stats) {
        if (!this.successChart) return;

        this.successChart.data.datasets[0].data = [
            stats.successful_requests,
            stats.failed_requests
        ];
        this.successChart.update();
    }

    /**
     * 更新所有图表
     */
    updateCharts(stats) {
        this.updateStatusChart(stats);
        this.updateSuccessChart(stats);
    }
}

// 全局图表管理器实例
const chartsManager = new ChartsManager();
