document.addEventListener("alpine:init", () => {
  Alpine.store("data", {
    search: "",
    jobs: [],
    tasks: [],
    logs: {},
    analytics: {
      recentActivity: [],
      upcomingExecutions: [],
      executionHistory: [],
      taskDistribution: [],
    },
    notifier: new NotificationManager(),
    loading: false,
    tableState: {
      logs: {
        page: 0,
        length: 25,
        search: "",
        order: [[1, "desc"]]
      }
    },

    get notifications() {
      return this.notifier.notifications;
    },

    // Computed metrics now only depend on analytics data
    metrics() {
      const totalLogs = this.logs.total;
      const errors = this.analytics.recentActivity.filter(
        (log) => log.status === "failed"
      );
      const errorRate = totalLogs
        ? Math.round((errors.length / totalLogs) * 100)
        : 0;

      return {
        tasks: this.tasks.length,
        jobs: this.jobs.length,
        logs: totalLogs,
        errors: { count: errors.length, rate: errorRate },
      };
    },

    // Specific fetch methods for each data type
    async fetchDashboardData() {
      this.notifier.showNotification("Syncing database...", "info", "ajax");
      try {
        await Promise.all([
          this.fetchTasks(),
          this.fetchJobs(),
          this.fetchLogs(),
          this.fetchAnalytics(),
        ]);
        this.notifier.showNotification("Data synced", "success", "ajax");
      } catch (e) {
        console.error("Error fetching data:", e);
        this.notifier.showNotification("Failed to fetch data", "error", "ajax");
      }
    },

    async fetchJobs() {
      this.loading = true;
      try {
        const response = await fetch("/api/jobs");
        if (response.ok) {
          this.jobs = await response.json();
        }
      } catch (error) {
        console.error("Error fetching tasks:", error);
        this.notifier.showNotification("Failed to load jobs", "error", "ajax");
      } finally {
        this.loading = false;
      }
    },

    async fetchTasks() {
      this.loading = true;
      try {
        const response = await fetch("/api/tasks");
        if (response.ok) {
          this.tasks = await response.json();
        }
      } catch (error) {
        console.error("Error fetching tasks:", error);
        this.notifier.showNotification("Failed to load tasks", "error", "ajax");
      } finally {
        this.loading = false;
      }
    },

    async fetchLogs(params = {}) {
      this.loading = true;
      try {
        const queryParams = new URLSearchParams({
          offset: params.offset || 0,
          limit: params.limit || 25,
          ...params
        });
        
        const response = await fetch(`/api/logs?${queryParams}`);
        if (response.ok) {
          this.logs = await response.json();
        }
      } catch (error) {
        console.error("Error fetching logs:", error);
        this.notifier.showNotification("Failed to load logs", "error", "ajax");
      } finally {
        this.loading = false;
      }
    },

    async fetchAnalytics() {
      this.loading = true;
      try {
        const [activity, upcoming, history, distribution] = await Promise.all([
          fetch("/api/analytics/recent-activity").then((r) => r.json()),
          fetch("/api/analytics/upcoming-executions").then((r) => r.json()),
          fetch("/api/analytics/execution-history").then((r) => r.json()),
          fetch("/api/analytics/task-distribution").then((r) => r.json()),
        ]);

        this.analytics = {
          recentActivity: activity || [],
          upcomingExecutions: upcoming || [],
          executionHistory: history || [],
          taskDistribution: distribution || [],
        };
      } catch (error) {
        console.error("Error fetching analytics:", error);
        this.notifier.showNotification(
          "Failed to fetch analytics",
          "error",
          "ajax"
        );
      } finally {
        this.loading = false;
      }
    },

    // Table state management
    saveTableState(tableId, state) {
      this.tableState[tableId] = {
        ...this.tableState[tableId],
        ...state
      };
    },

    getTableState(tableId) {
      return this.tableState[tableId] || {};
    }
  });
});
